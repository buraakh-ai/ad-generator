import requests
import boto3
from datetime import datetime
import os

from dotenv import load_dotenv

load_dotenv()

# Facebook Page credentials
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN")

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
    filename   = f"fb_ad_{timestamp}.jpg"
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


def post_to_facebook(image_local_path, caption):
    # Step 1 — Upload image to S3
    image_url = upload_to_s3(image_local_path)
    print(f"[facebook] Posting image: {image_url}")

    # Step 2 — Post photo to Facebook Page using /photos endpoint
    post_url = f"https://graph.facebook.com/v21.0/{FACEBOOK_PAGE_ID}/photos"
    post_payload = {
        "url":          image_url,
        "message":      caption,
        "access_token": FACEBOOK_PAGE_TOKEN
    }

    print(f"[facebook] Creating photo post...")
    r      = requests.post(post_url, data=post_payload, timeout=60)
    result = r.json()

    print(f"[facebook] Response: {result}")

    if "id" not in result:
        raise Exception(f"Failed to post to Facebook: {result}")

    post_id = result["id"]
    print(f"[facebook] Posted successfully! Post ID: {post_id}")
    return post_id





