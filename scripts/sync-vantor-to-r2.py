#!/usr/bin/env python3
"""
Cloud-based Vantor → R2 sync script.
Runs in GitHub Actions with cloud bandwidth.
Uses boto3 for S3-compatible transfer.
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import boto3
import requests
from tqdm import tqdm

# Configuration
COLLECTION_URL = "https://vantor-opendata.s3.amazonaws.com/events/Venezuela-Earthquake-Jun-2026/collection.json"
R2_BUCKET = os.environ.get('S3_BUCKET', 'crisis-damage-intelligence')
R2_ENDPOINT = os.environ.get('S3_ENDPOINT_URL', '')
R2_PREFIX = "vantor/venezuela-earthquake-jun-2026"
STRATEGY = os.environ.get('STRATEGY', 'best')
DRY_RUN = os.environ.get('DRY_RUN', 'false').lower() == 'true'

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_r2_client():
    """Create S3 client for R2."""
    return boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
        region_name='auto'
    )

def fetch_json(url):
    """Fetch JSON from URL."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()

def format_size(size_bytes):
    """Format bytes to human readable."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024**2:
        return f"{size_bytes/1024:.1f}KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes/1024**2:.1f}MB"
    else:
        return f"{size_bytes/1024**3:.1f}GB"

def download_file(url, dest):
    """Download file with progress bar."""
    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    
    with open(dest, 'wb') as f, tqdm(
        total=total_size, unit='B', unit_scale=True, 
        desc=Path(dest).name[:30]
    ) as pbar:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                pbar.update(len(chunk))
    
    return dest.stat().st_size

def upload_to_r2(s3_client, local_path, r2_key):
    """Upload file to R2."""
    s3_client.upload_file(
        str(local_path),
        R2_BUCKET,
        r2_key,
        ExtraArgs={'ContentType': get_content_type(local_path)}
    )

def get_content_type(file_path):
    """Get content type based on extension."""
    ext = Path(file_path).suffix.lower()
    types = {
        '.tif': 'image/tiff',
        '.tiff': 'image/tiff',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.json': 'application/json',
        '.csv': 'text/csv',
        '.geojson': 'application/geo+json',
    }
    return types.get(ext, 'application/octet-stream')

def process_item(s3_client, item, temp_dir):
    """Process a single STAC item."""
    item_id = item['id']
    props = item['properties']
    
    log(f"Processing {item_id}")
    log(f"  Date: {props.get('datetime', 'unknown')}")
    log(f"  Vehicle: {props.get('vehicle_name', 'unknown')}")
    log(f"  Cloud cover: {props.get('eo:cloud_cover', 'N/A')}%")
    
    result = {
        "id": item_id,
        "datetime": props.get('datetime'),
        "vehicle": props.get('vehicle_name'),
        "cloud_cover": props.get('eo:cloud_cover'),
        "assets": {}
    }
    
    for asset_name, asset_info in item.get('assets', {}).items():
        url = asset_info['href']
        filename = Path(url).name
        r2_key = f"{R2_PREFIX}/{item_id}/{filename}"
        local_path = temp_dir / item_id / filename
        
        # Skip COGs for 'thumbs' strategy
        if STRATEGY == 'thumbs' and asset_name == 'visual':
            log(f"  ⏭️  Skipping COG (thumbs strategy)")
            continue
        
        log(f"  📥 {asset_name}: {filename}")
        
        if DRY_RUN:
            log(f"  📝 DRY RUN - Would upload to r2://{R2_BUCKET}/{r2_key}")
            result['assets'][asset_name] = {
                "r2_key": r2_key,
                "dry_run": True
            }
            continue
        
        try:
            # Download
            local_path.parent.mkdir(parents=True, exist_ok=True)
            size = download_file(url, local_path)
            log(f"  ✅ Downloaded: {format_size(size)}")
            
            # Upload to R2
            log(f"  ⬆️  Uploading to R2...")
            upload_to_r2(s3_client, local_path, r2_key)
            log(f"  ✅ Uploaded to r2://{R2_BUCKET}/{r2_key}")
            
            result['assets'][asset_name] = {
                "r2_key": r2_key,
                "size": size,
                "type": asset_info.get('type', 'unknown')
            }
            
        except Exception as e:
            log(f"  ❌ Error: {e}")
            result['assets'][asset_name] = {"error": str(e)}
        finally:
            # Clean up
            if local_path.exists():
                local_path.unlink()
    
    return result

def main():
    log("=" * 60)
    log("VANTOR → R2 SYNC")
    log(f"Strategy: {STRATEGY}")
    log(f"Dry run: {DRY_RUN}")
    log("=" * 60)
    
    # Initialize R2 client
    s3_client = get_r2_client()
    log("R2 client initialized")
    
    # Fetch collection
    log("Fetching STAC collection...")
    collection = fetch_json(COLLECTION_URL)
    
    item_links = [link for link in collection['links'] if link['rel'] == 'item']
    log(f"Found {len(item_links)} items")
    
    # Fetch all items
    items = []
    for link in item_links:
        items.append(fetch_json(link['href']))
    
    # Sort by quality (cloud cover ascending)
    items.sort(key=lambda x: x['properties'].get('eo:cloud_cover', 100))
    
    # Filter based on strategy
    if STRATEGY == 'best':
        # Top 6 by quality
        items = items[:6]
        log(f"Selected top {len(items)} items by quality")
    elif STRATEGY == 'thumbs':
        # All items, but only thumbnails
        log(f"Processing all {len(items)} items, thumbnails only")
    else:
        # All items, all assets
        log(f"Processing all {len(items)} items")
    
    # Process each item
    manifest = {
        "source": "Vantor Open Data Program",
        "collection_url": COLLECTION_URL,
        "license": "CC-BY-NC-4.0",
        "strategy": STRATEGY,
        "dry_run": DRY_RUN,
        "uploaded_at": datetime.now().isoformat(),
        "items": []
    }
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        for idx, item in enumerate(items, 1):
            log(f"\n[{idx}/{len(items)}] {'='*50}")
            result = process_item(s3_client, item, temp_path)
            manifest['items'].append(result)
            
            # Save progress
            manifest_path = Path('/tmp/vantor-manifest.json')
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
    
    # Final summary
    log("\n" + "=" * 60)
    log("SYNC COMPLETE")
    log("=" * 60)
    
    total_files = sum(len(item['assets']) for item in manifest['items'])
    total_bytes = sum(
        asset.get('size', 0)
        for item in manifest['items']
        for asset in item['assets'].values()
        if 'size' in asset
    )
    
    log(f"Items processed: {len(items)}")
    log(f"Files uploaded: {total_files}")
    log(f"Total size: {format_size(total_bytes)}")
    
    if DRY_RUN:
        log("\n⚠️  This was a DRY RUN. No files were actually uploaded.")
        log("   Run with dry_run=false to perform the actual upload.")
    
    # Print best images info
    log("\nBest quality images:")
    for item in manifest['items']:
        cloud = item.get('cloud_cover', 'N/A')
        dt = item.get('datetime', 'unknown')
        log(f"  {item['id']} | Cloud:{cloud}% | {dt}")

if __name__ == "__main__":
    main()
