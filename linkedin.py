import requests
import boto3
from datetime import datetime
import os

from dotenv import load_dotenv

load_dotenv()

# LinkedIn credentials
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_URN = os.getenv("LINKEDIN_PERSON_URN")

# AWS S3 credentials
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION")


def upload_to_s3(local_path):
    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename   = f"li_ad_{timestamp}.jpg"
    print(f"[s3] Uploading {local_path} to s3://{AWS_BUCKET_NAME}/{filename}...")
    s3.upload_file(
        local_path,
        AWS_BUCKET_NAME,
        filename,
        ExtraArgs={"ContentType": "image/jpeg", "ACL": "public-read"}
    )
    public_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{filename}"
    print(f"[s3] Uploaded successfully: {public_url}")
    return public_url


def get_person_urn():
    return "urn:li:member:ACoAAGJOnO8BmRosWD8pfCGENhJfJtNSwOf9CGY"


def register_and_upload_image(image_local_path, person_urn):
    """Register image upload with LinkedIn and upload the bytes."""
    headers = {
        "Authorization":             f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type":              "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }

    # Register the upload
    register_payload = {
        "registerUploadRequest": {
            "recipes":           ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner":             person_urn,
            "serviceRelationships": [{
                "relationshipType": "OWNER",
                "identifier":       "urn:li:userGeneratedContent"
            }]
        }
    }
    r = requests.post(
        "https://api.linkedin.com/v2/assets?action=registerUpload",
        headers=headers,
        json=register_payload,
        timeout=30
    )
    result = r.json()
    if r.status_code != 200:
        raise Exception(f"LinkedIn image registration failed: {result}")

    upload_url = result["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    asset      = result["value"]["asset"]
    print(f"[linkedin] Image registered — asset: {asset}")

    # Upload image bytes
    with open(image_local_path, "rb") as f:
        image_data = f.read()
    r = requests.put(
        upload_url,
        headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
        data=image_data,
        timeout=60
    )
    if r.status_code not in [200, 201]:
        raise Exception(f"LinkedIn image upload failed: {r.status_code} {r.text[:200]}")
    print(f"[linkedin] Image uploaded successfully")
    return asset


def post_to_linkedin(image_local_path, caption):
    print(f"[linkedin] Starting post process...")

    # Get person URN
    person_urn = get_person_urn()
    print(f"[linkedin] Person URN: {person_urn}")

    # Upload image to S3 (for backup) and register with LinkedIn
    upload_to_s3(image_local_path)
    asset = register_and_upload_image(image_local_path, person_urn)

    # Create the post
    headers = {
        "Authorization":             f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type":              "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    post_payload = {
        "author":          person_urn,
        "lifecycleState":  "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary":   {"text": caption},
                "shareMediaCategory": "IMAGE",
                "media": [{
                    "status":      "READY",
                    "description": {"text": caption[:200]},
                    "media":       asset,
                    "title":       {"text": "Ad"}
                }]
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    print(f"[linkedin] Creating post...")
    r      = requests.post(
        "https://api.linkedin.com/v2/ugcPosts",
        headers=headers,
        json=post_payload,
        timeout=60
    )
    result = r.json()

    if r.status_code not in [200, 201]:
        raise Exception(f"Failed to post to LinkedIn: {result}")

    post_id = result.get("id", "unknown")
    print(f"[linkedin] Posted successfully! Post ID: {post_id}")
    return post_id