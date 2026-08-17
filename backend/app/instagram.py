from __future__ import annotations

import os

import httpx

from app.models import InstagramFeed, InstagramPost, SourceRef

JAY_INSTAGRAM_PROFILE = "https://www.instagram.com/jaychou/"
INSTAGRAM_GRAPH_SOURCE = SourceRef(
    name="Instagram Graph API",
    url="https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media",
    license="Requires authorized Instagram Business/Creator access token",
)


def get_jay_instagram_feed(limit: int = 6) -> InstagramFeed:
    ig_user_id = os.getenv("JAY_INSTAGRAM_USER_ID")
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    api_version = os.getenv("META_GRAPH_API_VERSION", "v23.0")

    if not ig_user_id or not access_token:
        return InstagramFeed(
            configured=False,
            profile_url=JAY_INSTAGRAM_PROFILE,
            message=(
                "未配置 Instagram Graph API token。当前只能提供周杰伦 Instagram 主页链接；"
                "配置 JAY_INSTAGRAM_USER_ID 和 INSTAGRAM_ACCESS_TOKEN 后可读取最新媒体。"
            ),
            sources=[INSTAGRAM_GRAPH_SOURCE],
        )

    url = f"https://graph.facebook.com/{api_version}/{ig_user_id}/media"
    params = {
        "fields": "id,caption,media_type,media_url,permalink,timestamp",
        "limit": max(1, min(limit, 12)),
        "access_token": access_token,
    }
    try:
        response = httpx.get(url, params=params, timeout=8.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return InstagramFeed(
            configured=True,
            profile_url=JAY_INSTAGRAM_PROFILE,
            message=f"Instagram Graph API 请求失败：{exc}",
            sources=[INSTAGRAM_GRAPH_SOURCE],
        )

    posts = [InstagramPost(**item) for item in payload.get("data", []) if item.get("permalink")]
    return InstagramFeed(
        configured=True,
        profile_url=JAY_INSTAGRAM_PROFILE,
        message="已通过 Instagram Graph API 获取最新媒体。",
        posts=posts,
        sources=[INSTAGRAM_GRAPH_SOURCE],
    )
