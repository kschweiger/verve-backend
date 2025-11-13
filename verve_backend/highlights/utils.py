from datetime import timedelta

from verve_backend.models import (
    ActivityHighlight,
    ActivityHighlightPublic,
    HighlightMetric,
)


def get_public_highlight(data: ActivityHighlight) -> ActivityHighlightPublic:
    public_highlight = ActivityHighlightPublic.model_validate(data)
    if public_highlight.metric == HighlightMetric.DURATION:
        assert not isinstance(public_highlight.value, timedelta)
        public_highlight.value = timedelta(seconds=int(public_highlight.value))
    if public_highlight.metric in [
        HighlightMetric.AVG_POWER,
        HighlightMetric.MAX_POWER,
        HighlightMetric.AVG_POWER1MIN,
        HighlightMetric.AVG_POWER2MIN,
        HighlightMetric.AVG_POWER5MIN,
        HighlightMetric.AVG_POWER10MIN,
        HighlightMetric.AVG_POWER20MIN,
        HighlightMetric.AVG_POWER30MIN,
        HighlightMetric.AVG_POWER60MIN,
    ]:
        assert not isinstance(public_highlight.value, timedelta)
        public_highlight.value = int(public_highlight.value)
    return public_highlight
