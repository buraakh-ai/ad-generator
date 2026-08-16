from flask import Flask, request, jsonify, send_from_directory, Response
from generator import generate_ads, get_client, company_cache, AllProvidersExhaustedError, TextProviderSwitchedWarning
from events import pick_best_event
from image_generator import create_ad_image, save_chrome, CHROME_PATH, save_active_provider, load_config, get_providers, ProviderFailedError
import os

app = Flask(__name__)

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/generate", methods=["POST"])
def generate():
    try:
        data                = request.json
        company_name        = data.get("company_name", "")
        product_description = data.get("product_description", "")
        ad_idea             = data.get("ad_idea", "")
        event_context       = data.get("event_context", None)
        company_url         = data.get("company_url", None)

        ads, detected_name, detected_event, company_details = generate_ads(
            company_name, product_description, ad_idea, event_context, company_url
        )

        logo_url = company_details.get("logo_url") if company_details else None
        try:
            save_chrome(detected_name or company_name, ads.get("instagram", ""), logo_url)
        except Exception as ce:
            print(f"[chrome] Build failed (non-fatal): {ce}")

        return jsonify({
            "success":               True,
            "ads":                   ads,
            "detected_company_name": detected_name,
            "detected_event":        detected_event,
            "company_details":       company_details,
            "image_headline":        ads.get("image_headline", ""),
            "quality_score":         ads.get("quality_score", 0),
            "quality_reason":        ads.get("quality_reason", ""),
        })

    except TextProviderSwitchedWarning as w:
        return jsonify({
            "success":           False,
            "provider_switched": True,
            "from_provider":     w.from_provider,
            "to_provider":       w.to_provider,
            "error":             str(w)
        }), 200

    except AllProvidersExhaustedError as e:
        return jsonify({
            "success":   False,
            "exhausted": True,
            "error":     str(e)
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/retry-event", methods=["POST"])
def retry_event():
    try:
        data         = request.json
        company_name = data.get("company_name", "")
        company_url  = data.get("company_url", "")
        cache_key    = (company_url or company_name).lower().strip()

        if cache_key not in company_cache:
            return jsonify({"success": False,
                            "error": "No cached company data. Please generate from scratch first."}), 400

        company_data = company_cache[cache_key]["company_data"]
        new_event    = pick_best_event(company_name, company_data, get_client())

        ads, detected_name, detected_event, company_details = generate_ads(
            company_name=company_name, product_description="", ad_idea="",
            event_context=new_event, company_url=company_url or None
        )

        logo_url = company_details.get("logo_url") if company_details else None
        try:
            save_chrome(detected_name or company_name, ads.get("instagram", ""), logo_url)
        except Exception as ce:
            print(f"[chrome] Rebuild failed (non-fatal): {ce}")

        return jsonify({
            "success":               True,
            "ads":                   ads,
            "detected_company_name": detected_name,
            "detected_event":        detected_event,
            "company_details":       company_details,
            "image_headline":        ads.get("image_headline", ""),
            "quality_score":         ads.get("quality_score", 0),
            "quality_reason":        ads.get("quality_reason", ""),
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        data            = request.json
        company_name    = data.get("company_name", "")
        instagram_copy  = data.get("instagram_copy", "")
        image_headline  = data.get("image_headline", "")
        event_context   = data.get("event_context", "")
        company_details = data.get("company_details", {})
        logo_url        = data.get("logo_url", None)
        custom_prompt   = data.get("custom_prompt", "").strip()

        display_path, clean_path = create_ad_image(
            company_name, instagram_copy, image_headline,
            event_context, company_details, logo_url,
            chrome_path=CHROME_PATH,
            custom_prompt=custom_prompt or None
        )

        config   = load_config()
        provider = config.get("active_provider", "pollinations")

        return jsonify({
            "success":         True,
            "image_url":       "/" + display_path,
            "clean_image_url": "/" + clean_path,
            "provider":        provider
        })

    except ProviderFailedError as e:
        return jsonify({
            "success":             False,
            "provider_failed":     True,
            "failed_provider":     e.failed_provider,
            "next_provider_name":  e.next_provider_name,
            "next_provider_label": e.next_provider_label,
            "error":               str(e)
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/switch-image-provider", methods=["POST"])
def switch_image_provider():
    try:
        data     = request.json
        provider = data.get("provider", "")
        if not provider:
            return jsonify({"success": False, "error": "No provider specified"}), 400
        save_active_provider(provider)
        return jsonify({"success": True, "provider": provider})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/get-image-providers", methods=["GET"])
def get_image_providers():
    try:
        config    = load_config()
        providers = get_providers(config)
        active    = config.get("active_provider", "pollinations")
        return jsonify({"success": True, "providers": providers, "active": active})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/post-to-instagram", methods=["POST"])
def post_instagram():
    try:
        from instagram import post_to_instagram
        data      = request.json
        caption   = data.get("caption", "")
        image_url = data.get("image_url", "")

        if "static/" in image_url:
            local_path = "static/" + image_url.split("static/")[-1].split("?")[0]
        else:
            local_path = image_url.lstrip("/").split("?")[0]

        print(f"[instagram] Local path resolved: {local_path}")

        if not os.path.exists(local_path):
            return jsonify({"success": False, "error": f"Image file not found: {local_path}"}), 400

        post_id = post_to_instagram(local_path, caption)
        return jsonify({"success": True, "post_id": post_id})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/post-to-facebook", methods=["POST"])
def post_facebook():
    try:
        from facebook import post_to_facebook
        data      = request.json
        caption   = data.get("caption", "")
        image_url = data.get("image_url", "")

        if "static/" in image_url:
            local_path = "static/" + image_url.split("static/")[-1].split("?")[0]
        else:
            local_path = image_url.lstrip("/").split("?")[0]

        print(f"[facebook] Local path resolved: {local_path}")

        if not os.path.exists(local_path):
            return jsonify({"success": False, "error": f"Image file not found: {local_path}"}), 400

        post_id = post_to_facebook(local_path, caption)
        return jsonify({"success": True, "post_id": post_id})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/post-to-linkedin", methods=["POST"])
def post_linkedin():
    try:
        from linkedin import post_to_linkedin
        data      = request.json
        caption   = data.get("caption", "")
        image_url = data.get("image_url", "")

        if "static/" in image_url:
            local_path = "static/" + image_url.split("static/")[-1].split("?")[0]
        else:
            local_path = image_url.lstrip("/").split("?")[0]

        print(f"[linkedin] Local path resolved: {local_path}")

        if not os.path.exists(local_path):
            return jsonify({"success": False, "error": f"Image file not found: {local_path}"}), 400

        post_id = post_to_linkedin(local_path, caption)
        return jsonify({"success": True, "post_id": post_id})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

@app.route("/call-count")
def call_count():
    from generator import call_counter
    return jsonify({"count": call_counter["count"]})

if __name__ == "__main__":
    app.run(debug=True)