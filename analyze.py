"""
Builds the data files that dashboard.html renders directly: the
creator-level dataset, the view-concentration curve, and the
content-signal statistics. Shares its core logic with
build_qa_digest.py via creator_analysis.py.
"""

import json
import os

from creator_analysis import (
    load_data,
    compute_creator_table,
    compute_headline_stats,
    compute_content_signals,
    compute_reach_concentration,
)


def build_creator_data(df, creator, thresholds):
    """dashboard.html's charts and table: headline stats, every
    creator's scatter point, the ranked top 20, and trimmed video-level
    rows for the Q&A to fall back on if needed."""
    headline = compute_headline_stats(df, creator)

    top20 = creator.sort_values('promise_score', ascending=False).head(20)
    top20_records = top20[
        ['author_name', 'total_views', 'max_views', 'avg_engagement', 'verified', 'videos', 'promise_score']
    ].round({'avg_engagement': 4, 'promise_score': 3}).to_dict(orient='records')

    scatter = creator[['author_name', 'total_views', 'avg_engagement', 'verified', 'repeat_creator', 'promising']].copy()
    scatter['avg_engagement'] = scatter['avg_engagement'].round(4)
    scatter_records = scatter.to_dict(orient='records')

    video_export = df[[
        'author_name', 'views', 'likes', 'comments', 'shares', 'author_verified',
        'engagement_rate', 'duration_sec', 'upload_date', 'primary_hashtag',
        'music_is_original', 'caption',
    ]].copy()
    video_export['engagement_rate'] = video_export['engagement_rate'].round(4)
    video_export['upload_date'] = video_export['upload_date'].dt.strftime('%Y-%m-%d')
    video_records = video_export.to_dict(orient='records')

    return {
        'headline': headline,
        'scatter': scatter_records,
        'top20': top20_records,
        'videos': video_records,
        'thresholds': thresholds,
    }


def build_view_concentration(creator):
    """The Lorenz-style curve behind the 'where the views concentrate' chart."""
    by_views = creator.sort_values('total_views', ascending=False).reset_index(drop=True)
    by_views['cum_views_pct'] = 100 * by_views['total_views'].cumsum() / by_views['total_views'].sum()
    by_views['creator_rank_pct'] = 100 * (by_views.index + 1) / len(by_views)

    n = len(by_views)
    sample_idx = sorted(set([int(n * p / 100) for p in range(0, 101, 2)] + [n - 1]))
    sample_idx = [i for i in sample_idx if i < n]
    curve = [
        {'x': round(by_views.loc[i, 'creator_rank_pct'], 1), 'y': round(by_views.loc[i, 'cum_views_pct'], 1)}
        for i in sample_idx
    ]

    concentration = compute_reach_concentration(creator)
    return {
        'curve': curve,
        'top10_views_share': concentration['top_10_creators_by_raw_views_share_of_total_views_pct'],
        'top50_views_share': concentration['top_50_creators_by_raw_views_share_of_total_views_pct'],
    }


def build_content_signals(df, creator, top3_names):
    """The 'what does the content itself do' card, plus each of the
    top 3 verdict creators' best-performing individual video."""
    signals = compute_content_signals(df)

    top3_best_videos = {}
    for name in top3_names:
        sub = df[df.author_name == name].sort_values('engagement_rate', ascending=False)
        best = sub.iloc[0]
        top3_best_videos[name] = {
            'engagement_rate': round(float(best.engagement_rate), 4),
            'duration_sec': int(best.duration_sec),
            'original_sound': bool(best.music_is_original),
            'caption': str(best.caption)[:120] if str(best.caption) != 'nan' else None,
        }

    return {
        'content_signals': {
            'duration_buckets': signals['duration_buckets_median_engagement'],
            'duration_engagement_correlation': signals['duration_engagement_correlation'],
            'original_sound_median': signals['original_sound_median_engagement'],
            'trending_sound_median': signals['trending_sound_median_engagement'],
            'hashtag_makes_no_difference': signals['hashtag_presence_makes_no_meaningful_difference'],
        },
        'top3_best_videos': top3_best_videos,
    }


def write_json(obj, path):
    with open(path, 'w') as f:
        json.dump(obj, f)
    print(f"{path}: {os.path.getsize(path) / 1024:.1f} KB")


if __name__ == '__main__':
    df = load_data()
    creator, thresholds = compute_creator_table(df)

    creator_data = build_creator_data(df, creator, thresholds)
    write_json(creator_data, 'creator_data.json')

    view_concentration = build_view_concentration(creator)
    write_json(view_concentration, 'view_concentration.json')

    top3_names = creator.sort_values('promise_score', ascending=False).head(3)['author_name'].tolist()
    content_signals = build_content_signals(df, creator, top3_names)
    write_json(content_signals, 'content_signals.json')

    print("\nHeadline:", json.dumps(creator_data['headline'], indent=2))
    print("Top 5 promising:")
    for r in creator_data['top20'][:5]:
        print(r)
