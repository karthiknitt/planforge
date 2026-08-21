from app.engine.style_presets import STYLE_PRESETS, preset_programme


def test_all_eighteen_corpus_styles_are_present():
    assert len(STYLE_PRESETS) == 18
    for name in ("Kerala", "Chettinad", "Goan", "Rajasthani-Haveli"):
        assert name in STYLE_PRESETS


def test_kerala_seeds_a_courtyard_and_open_car_porch():
    prog = preset_programme("Kerala")
    assert "courtyard" in prog
    assert "car_porch_open" in prog


def test_prevalence_percentages_match_the_corpus():
    """These numbers are quoted to users in the UI, so they must not drift.

    All four are tabulated in docs/superpowers/specs/solver_capability_gaps.md
    section 6.
    """
    assert STYLE_PRESETS["Goan"].prevalence["courtyard"] == 33
    assert STYLE_PRESETS["Colonial"].prevalence["car_porch_open"] == 70
    assert STYLE_PRESETS["Bengali"].prevalence["verandah"] == 23
    assert STYLE_PRESETS["Chettinad"].prevalence["terrace"] == 45


def test_median_plot_and_bhk_match_the_corpus():
    """Recomputed 2026-08-21 from reverse_engr *-data.json metadata (median
    Plot Size, modal Type). Sivavela-01 has no data.json — its values come
    from its OCR: a 32'10" x 36'1" plot and two bedrooms.
    """
    assert STYLE_PRESETS["Kerala"].median_plot_sqft == 2091
    assert STYLE_PRESETS["Assamese"].typical_bhk == "2 BHK"
    assert STYLE_PRESETS["Sivavela"].median_plot_sqft == 1185
    assert STYLE_PRESETS["Tibetan-Buddhist"].typical_bhk == "4 BHK"


def test_only_features_above_a_quarter_prevalence_are_pre_ticked():
    """A feature present in <25% of a style's designs is a bad default."""
    for name, preset in STYLE_PRESETS.items():
        for flag in preset_programme(name):
            assert preset.prevalence[flag] >= 25, (
                f"{name} pre-ticks {flag} at only {preset.prevalence[flag]}%"
            )


def test_unknown_style_yields_an_empty_programme():
    assert preset_programme("Atlantean") == set()


async def test_style_presets_endpoint_serves_all_presets(client):
    response = await client.get("/api/style-presets")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 18
    kerala = body["Kerala"]
    assert kerala["typical_bhk"] == "4 BHK"
    assert kerala["prevalence"]["courtyard"] == 30
