"""Tests for the onboarding relevance scorer."""

from strategy_hunter.onboarding.relevance import onboarding_relevance_score


def test_empty_text_scores_zero():
    assert onboarding_relevance_score("") == 0


def test_referral_signup_string_scores_positive():
    text = "Get a $50 sign-up bonus when you refer a friend using a referral code."
    assert onboarding_relevance_score(text) > 0


def test_off_topic_string_scores_zero():
    # Completely unrelated content — no signal phrases
    text = "The weather in Sydney today is partly cloudy with a high of 18 degrees."
    assert onboarding_relevance_score(text) == 0


def test_cashback_is_a_signal():
    assert onboarding_relevance_score("100% cashback for new customers") > 0


def test_new_member_is_a_signal():
    assert onboarding_relevance_score("Welcome bonus for new member signup") > 0


def test_case_insensitive():
    assert onboarding_relevance_score("REFERRAL CODE REQUIRED") > 0
