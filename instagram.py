import requests
import boto3
import time
from datetime import datetime
import os

from dotenv import load_dotenv

load_dotenv()

# Instagram credentials
INSTAGRAM_USER_ID = os.getenv("INSTAGRAM_USER_ID")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")

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
    filename   = f"ad_{timestamp}.jpg"
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


def check_media_status(container_id, max_attempts=10):
    """Poll Instagram until the media container is ready to publish."""
    status_url = f"https://graph.instagram.com/v21.0/{container_id}"
    for attempt in range(max_attempts):
        r      = requests.get(status_url, params={
            "fields":       "status_code,status",
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }, timeout=30)
        result = r.json()
        status = result.get("status_code", "")
        print(f"[instagram] Media status check {attempt+1}/{max_attempts}: {status}")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            raise Exception(f"Media processing failed: {result}")
        time.sleep(3)
    return False


def post_to_instagram(image_local_path, caption):
    # Step 1 — Upload image to S3 to get a public URL
    image_url = upload_to_s3(image_local_path)
    print(f"[instagram] Posting image: {image_url}")

    # Step 2 — Create media container on Instagram
    container_url     = f"https://graph.instagram.com/v21.0/{INSTAGRAM_USER_ID}/media"
    container_payload = {
        "image_url":    image_url,
        "caption":      caption,
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }
    print(f"[instagram] Creating media container...")
    r      = requests.post(container_url, data=container_payload, timeout=60)
    result = r.json()

    if "id" not in result:
        raise Exception(f"Failed to create container: {result}")

    container_id = result["id"]
    print(f"[instagram] Container created: {container_id}")

    # Step 3 — Wait for Instagram to finish processing the media
    print(f"[instagram] Waiting for media to be ready...")
    ready = check_media_status(container_id)
    if not ready:
        print(f"[instagram] Status check inconclusive — waiting 10 extra seconds...")
        time.sleep(10)

    # Step 4 — Publish the container
    publish_url     = f"https://graph.instagram.com/v21.0/{INSTAGRAM_USER_ID}/media_publish"
    publish_payload = {
        "creation_id":  container_id,
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }
    print(f"[instagram] Publishing post...")
    r      = requests.post(publish_url, data=publish_payload, timeout=60)
    result = r.json()

    if "id" not in result:
        raise Exception(f"Failed to publish: {result}")

    print(f"[instagram] Posted successfully! Post ID: {result['id']}")
    return result["id"]