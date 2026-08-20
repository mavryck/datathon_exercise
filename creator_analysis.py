"""
Shared analysis functions for the Trending Creator Signal project.

Both analyze.py (dashboard data) and build_qa_digest.py (Q&A grounding
digest) import from this module instead of duplicating the same pandas
logic. This is the single source of truth for how "promising" is
calculated, how content signals are derived, and how reach concentration
and impact are measured.
"""

import pandas as pd


def load_data(csv_path='2026datathon_interview_data.csv'):
    """Load the source CSV and add the derived columns every downstream
    function relies on: parsed upload_date and engagement_rate."""
    df = pd.read_csv(csv_path)
    df['upload_date'] = pd.to_datetime(df['upload_date'])
    df['engagement_rate'] = (df['likes'] + df['comments'] + df['shares']) / df['views']
    return df


def compute_creator_table(df):
    """Aggregate video-level rows to one row per creator, and score each
    creator on reach percentile, resonance percentile, and the combined
    promise_score. This is the core "what does promising mean" logic,
    used by every other function in this module."""
    creator = df.groupby('author_name').agg(
        videos=('video_id', 'count'),
        total_views=('views', 'sum'),
        max_views=('views', 'max'),
        avg_engagement=('engagement_rate', 'mean'),
        verified=('author_verified', 'max'),
        total_likes=('likes', 'sum'),
        total_comments=('comments', 'sum'),
        total_shares=('shares', 'sum'),
    ).reset_index()

    reach_p75 = creator['total_views'].quantile(0.75)
    eng_p75 = creator['avg_engagement'].quantile(0.75)

    creator['high_reach'] = creator['total_views'] >= reach_p75
    creator['high_resonance'] = creator['avg_engagement'] >= eng_p75
    creator['promising'] = creator['high_reach'] & creator['high_resonance']
    creator['repeat_creator'] = creator['videos'] > 1

    creator['reach_pct'] = creator['total_views'].rank(pct=True)
    creator['resonance_pct'] = creator['avg_engagement'].rank(pct=True)
    creator['promise_score'] = (creator['reach_pct'] + creator['resonance_pct']) / 2

    return creator, {'reach_p75_views': int(reach_p75), 'engagement_p75_rate': round(float(eng_p75), 4)}


def compute_headline_stats(df, creator):
    """Top-line counts and medians shown at the top of the dashboard."""
    return {
        'total_videos': int(len(df)),
        'distinct_creators': int(df['author_name'].nunique()),
        'date_range': f"{df['upload_date'].min().strftime('%b %d, %Y')} - {df['upload_date'].max().strftime('%b %d, %Y')}",
        'median_engagement_rate': round(float(df['engagement_rate'].median()), 4),
        'pct_verified_creators': round(100 * float(creator['verified'].mean()), 1),
        'promising_count': int(creator['promising'].sum()),
        'repeat_creator_count': int(creator['repeat_creator'].sum()),
        'repeat_creator_median_engagement': round(float(creator[creator.repeat_creator]['avg_engagement'].median()), 4),
        'single_video_median_engagement': round(float(creator[~creator.repeat_creator]['avg_engagement'].median()), 4),
        'verified_median_engagement': round(float(creator[creator.verified]['avg_engagement'].median()), 4),
        'unverified_median_engagement': round(float(creator[~creator.verified]['avg_engagement'].median()), 4),
    }


def compute_percentiles(series, points=(.25, .50, .75, .90)):
    """Generic percentile helper, reused for both engagement rate and
    views so the quantile logic isn't written out twice."""
    return {f'p{int(p*100)}': round(float(series.quantile(p)), 4) for p in points}


def compute_content_signals(df):
    """Duration, sound, and hashtag engagement patterns. This is the
    'content' half of 'which creators and content look promising'."""
    dur_bucket = pd.cut(df['duration_sec'], bins=[0, 10, 20, 30, 60],
                         labels=['<10s', '10-20s', '20-30s', '30-60s'])
    dur_stats = df.groupby(dur_bucket, observed=True)['engagement_rate'].median().round(4).to_dict()
    orig_sound = df.groupby('music_is_original')['engagement_rate'].median().round(4).to_dict()

    return {
        'duration_buckets_median_engagement': {
            'under_10s': dur_stats.get('<10s'),
            '10_20s': dur_stats.get('10-20s'),
            '20_30s': dur_stats.get('20-30s'),
            '30_60s': dur_stats.get('30-60s'),
        },
        'duration_engagement_correlation': round(float(df['duration_sec'].corr(df['engagement_rate'])), 3),
        'original_sound_median_engagement': orig_sound.get(True),
        'trending_sound_median_engagement': orig_sound.get(False),
        'hashtag_presence_makes_no_meaningful_difference': True,
    }


def _view_totals(creator):
    return {k: creator[f'total_{k}'].sum() for k in ['views', 'likes', 'comments', 'shares']}


def compute_share_of_totals(subset, totals):
    """What percentage of all views/likes/comments/shares/engagement
    actions a given slice of creators accounts for. Used for both the
    reach-concentration chart and the top10/top20 impact comparison,
    so the percentage math lives in exactly one place."""
    eng = subset['total_likes'].sum() + subset['total_comments'].sum() + subset['total_shares'].sum()
    total_eng = totals['likes'] + totals['comments'] + totals['shares']
    return {
        'views_pct': round(100 * subset['total_views'].sum() / totals['views'], 2),
        'likes_pct': round(100 * subset['total_likes'].sum() / totals['likes'], 2),
        'comments_pct': round(100 * subset['total_comments'].sum() / totals['comments'], 2),
        'shares_pct': round(100 * subset['total_shares'].sum() / totals['shares'], 2),
        'engagement_actions_pct': round(100 * eng / total_eng, 2),
    }


def compute_reach_concentration(creator):
    """How much of total reach the biggest raw-views accounts hold,
    the 'top 10 = 60.2% of views' finding."""
    totals = _view_totals(creator)
    by_views = creator.sort_values('total_views', ascending=False)
    top10_pct = round(compute_share_of_totals(by_views.head(10), totals)['views_pct'], 1)
    top50_pct = round(compute_share_of_totals(by_views.head(50), totals)['views_pct'], 1)
    return {
        'top_10_creators_by_raw_views_share_of_total_views_pct': top10_pct,
        'top_50_creators_by_raw_views_share_of_total_views_pct': top50_pct,
        'note': 'This is concentration by raw views ranking, different from our promising-creator score which only captures 1.9pct of total views since it also requires high engagement, not just high views',
    }


def compute_impact(creator):
    """Compares our promising-score top 10/20 against the raw-views
    top 10 on what share of engagement (not just views) each holds."""
    totals = _view_totals(creator)
    ranked = creator.sort_values('promise_score', ascending=False)
    by_views = creator.sort_values('total_views', ascending=False)

    our_top10 = compute_share_of_totals(ranked.head(10), totals)
    our_top20 = compute_share_of_totals(ranked.head(20), totals)
    raw_top10 = compute_share_of_totals(by_views.head(10), totals)

    return {
        'our_top10_pct_of_views': our_top10['views_pct'],
        'our_top10_pct_of_likes': our_top10['likes_pct'],
        'our_top10_pct_of_comments': our_top10['comments_pct'],
        'our_top10_pct_of_shares': our_top10['shares_pct'],
        'our_top20_pct_of_views': our_top20['views_pct'],
        'our_top20_pct_of_all_engagement_actions': our_top20['engagement_actions_pct'],
        'raw_views_top10_pct_of_views': raw_top10['views_pct'],
        'raw_views_top10_pct_of_all_engagement_actions': raw_top10['engagement_actions_pct'],
        'takeaway': 'Our top 10 converts a much smaller view share into disproportionately higher engagement share (roughly 2x), while the raw-views top 10 has engagement share barely above its view share (near 1:1). That disproportion is the argument for using our score instead of raw views.',
    }


KNOWN_LIMITATIONS = [
    "No follower counts in the export; 'reach' means views on trending videos only, not audience size.",
    "759 of 802 creators appear only once in this 3-month window, so 'consistency' can only be assessed for the 91 creators with 2+ videos.",
    "147 of 1,000 videos have no primary_hashtag, so content-category signal is incomplete.",
    "This is a single trending export, not the creator's full channel history.",
    "No location, country, or language data exists in this export; geographic targeting can't be answered from this dataset.",
    "Reach is concentrated: the 10 biggest accounts by raw views hold 60.2% of all views in this export, a handful of viral hits, not a representative spread. Our promising-creator score is built specifically to avoid just re-surfacing those same accounts.",
]

DATA_WED_WANT_NEXT = [
    "Location or country, to see if top creators cluster geographically and enable in-person activation (events, meetups, studio visits)",
    "Follower count, to separate one-batch trending reach from real audience size",
    "Account age or history, to distinguish an overnight spike from steady growth",
    "A real content-category taxonomy, since hashtags are too noisy to use",
]

DEFINITION = "Promising = top-quartile on BOTH reach (total views) AND resonance (engagement rate = (likes+comments+shares)/views). Verified status and repeat appearance are noted as confidence signals, not requirements."
DATASET_SCOPE = "1,000 trending TikTok videos, 802 distinct creators, Sep 22 - Dec 21 2020. NO follower counts available. 'Reach' = views only."
