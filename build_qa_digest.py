"""
Builds qa_digest.json, the compact set of facts dashboard.html sends
to Claude with every Q&A question. Shares its core logic with
analyze.py via creator_analysis.py, so the numbers here are guaranteed
to match what the dashboard itself displays.
"""

import json
import os

from creator_analysis import (
    load_data,
    compute_creator_table,
    compute_headline_stats,
    compute_percentiles,
    compute_content_signals,
    compute_reach_concentration,
    compute_impact,
    DEFINITION,
    DATASET_SCOPE,
    KNOWN_LIMITATIONS,
    DATA_WED_WANT_NEXT,
)


def build_digest(df, creator):
    headline = compute_headline_stats(df, creator)

    top15 = creator.sort_values('promise_score', ascending=False).head(15)[
        ['author_name', 'total_views', 'avg_engagement', 'verified', 'videos']
    ].round(4).to_dict(orient='records')

    hashtag_counts = df['primary_hashtag'].value_counts().head(10).to_dict()

    return {
        'definition': DEFINITION,
        'dataset_scope': DATASET_SCOPE,
        'headline_stats': {
            'total_videos': headline['total_videos'],
            'distinct_creators': headline['distinct_creators'],
            'median_engagement_rate': headline['median_engagement_rate'],
            'pct_creators_verified': headline['pct_verified_creators'],
            'promising_creator_count': headline['promising_count'],
            'creators_appearing_more_than_once': headline['repeat_creator_count'],
            'pct_creators_single_video': round(100 - headline['repeat_creator_count'] / headline['distinct_creators'] * 100, 1),
        },
        'engagement_by_segment': {
            'verified_median_engagement': headline['verified_median_engagement'],
            'unverified_median_engagement': headline['unverified_median_engagement'],
            'repeat_creator_median_engagement': headline['repeat_creator_median_engagement'],
            'single_video_creator_median_engagement': headline['single_video_median_engagement'],
            'original_sound_median_engagement': compute_content_signals(df)['original_sound_median_engagement'],
            'trending_sound_median_engagement': compute_content_signals(df)['trending_sound_median_engagement'],
        },
        'top_15_promising_creators': top15,
        'top_10_hashtags_by_video_count': hashtag_counts,
        'engagement_rate_percentiles': compute_percentiles(df['engagement_rate']),
        'views_percentiles': {k: int(v) for k, v in compute_percentiles(df['views']).items()},
        'content_signals': compute_content_signals(df),
        'top10_top20_impact_vs_raw_views_top10': compute_impact(creator),
        'reach_concentration': compute_reach_concentration(creator),
        'data_wed_want_next': DATA_WED_WANT_NEXT,
        'known_limitations': KNOWN_LIMITATIONS,
    }


if __name__ == '__main__':
    df = load_data()
    creator, _ = compute_creator_table(df)
    digest = build_digest(df, creator)

    with open('qa_digest.json', 'w') as f:
        json.dump(digest, f, indent=2)

    print("qa_digest.json written")
    print(f"size KB: {os.path.getsize('qa_digest.json') / 1024:.2f}")
