from hypothesis import given
from hypothesis import strategies as st

from experimentlens.metrics import absolute_lift, conversion_rate, relative_lift


@given(st.integers(min_value=0, max_value=1000), st.integers(min_value=0, max_value=1000))
def test_rates_and_p_values_are_bounded(successes, trials):
    successes = min(successes, trials)
    rate = conversion_rate(successes, trials)
    assert rate is None or 0 <= rate <= 1

@given(st.floats(min_value=0, max_value=1), st.floats(min_value=0, max_value=1))
def test_absolute_lift_has_declared_order(control, treatment):
    assert absolute_lift(control, treatment) == treatment - control
    assert absolute_lift(treatment, control) == -absolute_lift(control, treatment)

@given(st.floats(min_value=0.0001, max_value=1), st.floats(min_value=0, max_value=1))
def test_relative_lift_matches_definition(control, treatment):
    assert relative_lift(control, treatment) == (treatment - control) / control
