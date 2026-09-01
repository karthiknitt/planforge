from app.engine.corpus_priors import (
    get_adjacency_prior,
    get_position_prior,
    get_shape_usage_prior,
    get_size_prior,
    load_priors,
)
from app.engine.models import PlotConfig


def _cfg(style: str | None) -> PlotConfig:
    return PlotConfig(
        plot_y_extent=10.0,
        plot_x_extent=10.0,
        setback_front=1.0,
        setback_rear=1.0,
        setback_left=1.0,
        setback_right=1.0,
        num_bedrooms=1,
        toilets=1,
        parking=False,
        style_preset=style,
    )


def test_get_size_prior_returns_something_for_a_known_room_type() -> None:
    prior = get_size_prior(_cfg(None), "kitchen")
    assert prior is not None
    assert prior.area_mean > 0


def test_get_size_prior_falls_back_for_unknown_style() -> None:
    corpus_wide = get_size_prior(_cfg(None), "kitchen")
    unknown_style = get_size_prior(_cfg("NotARealStyle"), "kitchen")
    assert unknown_style == corpus_wide


def test_get_size_prior_falls_back_when_style_lacks_the_room_type() -> None:
    # "Assamese" has no "courtyard" entry in its own rooms block.
    corpus_wide = get_size_prior(_cfg(None), "courtyard")
    style_specific = get_size_prior(_cfg("Assamese"), "courtyard")
    assert style_specific == corpus_wide


def test_get_adjacency_prior_returns_positive_for_a_common_pair() -> None:
    assert get_adjacency_prior(_cfg(None), "bedroom", "toilet") > 0


def test_get_adjacency_prior_is_symmetric_in_argument_order() -> None:
    forward = get_adjacency_prior(_cfg(None), "bedroom", "toilet")
    reverse = get_adjacency_prior(_cfg(None), "toilet", "bedroom")
    assert forward == reverse


def test_get_adjacency_prior_falls_back_when_style_lacks_the_pair() -> None:
    corpus_wide = get_adjacency_prior(_cfg(None), "bedroom", "toilet")
    style_specific = get_adjacency_prior(_cfg("Assamese"), "bedroom", "courtyard")
    corpus_wide_pair = get_adjacency_prior(_cfg(None), "bedroom", "courtyard")
    assert style_specific == corpus_wide_pair
    assert corpus_wide >= 0


def test_get_position_prior_returns_plausible_value_for_known_zone() -> None:
    value = get_position_prior(_cfg("Kerala"), "kitchen", "C")
    assert 0.0 <= value <= 1.0
    assert value > 0.0


def test_get_position_prior_returns_zero_for_unknown_zone() -> None:
    assert get_position_prior(_cfg("Kerala"), "kitchen", "NOT_A_ZONE") == 0.0


def test_get_position_prior_returns_zero_when_no_style_given() -> None:
    # corpus_priors.json has no corpus-wide position table -- only per-style.
    assert get_position_prior(_cfg(None), "kitchen", "C") == 0.0


def test_get_shape_usage_prior_returns_real_value_for_known_room_type() -> None:
    value = get_shape_usage_prior(_cfg("Kerala"), "kitchen")
    assert value == 0.125


def test_get_shape_usage_prior_returns_zero_when_no_style_given() -> None:
    # corpus_priors.json has no corpus-wide shape_usage table -- only per-style.
    assert get_shape_usage_prior(_cfg(None), "kitchen") == 0.0


def test_load_priors_parses_the_artifact_only_once() -> None:
    """Every accessor calls this per lookup; the adjacency term, O(n^2) times.

    Identity, not equality: two equal dicts would mean the 173 KB file was
    re-read and re-parsed, which is exactly what the cache exists to stop.
    """
    assert load_priors() is load_priors()
