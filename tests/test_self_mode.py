"""V7 — end-to-end self-mode cascade tests."""

import json

from agents import cascade_graph
from agents.schemas import (
    BusinessProfile,
    CascadeBrief,
    CascadeMode,
    SharedBundle,
    SourceItem,
    SourceSubject,
    SourceType,
    Stage,
)
from fixtures.fake_llm import (
    fake_finance_llm,
    fake_gtm_llm,
    fake_marketing_llm,
    fake_security_llm,
    fake_strategy_llm,
)
from fixtures.sample import sample_bundle

_FAKES = dict(
    gtm_llm=fake_gtm_llm,
    finance_llm=fake_finance_llm,
    marketing_llm=fake_marketing_llm,
    security_llm=fake_security_llm,
    strategy_llm=fake_strategy_llm,
)


def _profile() -> BusinessProfile:
    return BusinessProfile(
        name="Northwind Analytics",
        url="https://northwind.example/",
        industry="B2B data analytics",
        stage=Stage.GROWTH,
        goal="Win 50 EU enterprise logos this year",
        customer_segment="Mid-market RevOps + Finance",
        competitor_urls=[],
        competitor_names=["Tableau", "Looker", "ThoughtSpot"],
    )


def test_self_mode_brief_has_business_profile_and_marketing():
    brief = cascade_graph.run(
        sample_bundle(),
        mode=CascadeMode.SELF,
        business_profile=_profile(),
        **_FAKES,
    )
    assert isinstance(brief, CascadeBrief)
    assert brief.mode == CascadeMode.SELF
    assert brief.business_profile is not None
    assert brief.business_profile.name == "Northwind Analytics"
    assert brief.business_profile.stage == Stage.GROWTH
    # Marketing dept always runs (V7+)
    assert brief.marketing_signal is not None
    assert brief.marketing_signal.all_claims()


def test_self_mode_strategic_plan_present():
    brief = cascade_graph.run(
        sample_bundle(),
        mode=CascadeMode.SELF,
        business_profile=_profile(),
        **_FAKES,
    )
    assert brief.strategic_plan is not None
    assert brief.strategic_plan.recommended_plays


def test_source_subject_tagged_in_bundle():
    """A self-mode bundle tags each source so the marketing prompt can
    distinguish 'your site' from 'competitor's site'."""
    bundle = SharedBundle(
        target="MyShop",
        sources=[
            SourceItem(
                source_type=SourceType.SITE, url="https://my.example/",
                text="we sell beans",
                subject=SourceSubject.SELF,
            ),
            SourceItem(
                source_type=SourceType.SITE, url="https://comp.example/",
                text="we sell ground beans cheaper",
                subject=SourceSubject.COMPETITOR,
                competitor_name="comp.example",
            ),
        ],
    )
    assert len(bundle.texts_by_subject(SourceSubject.SELF)) == 1
    assert len(bundle.texts_by_subject(SourceSubject.COMPETITOR)) == 1
    assert bundle.competitor_names() == ["comp.example"]


def test_self_mode_events_include_marketing(tmp_path):
    events_file = tmp_path / "events.jsonl"
    cascade_graph.run(
        sample_bundle(),
        mode=CascadeMode.SELF,
        business_profile=_profile(),
        event_path=events_file,
        **_FAKES,
    )
    events = [json.loads(l) for l in events_file.read_text().splitlines() if l.strip()]
    marketing_done = [
        e for e in events
        if e.get("phase") == "dept" and e.get("dept") == "marketing" and e.get("status") == "done"
    ]
    assert marketing_done, "expected marketing dept-done event"
    assemble = [e for e in events if e.get("phase") == "assemble"]
    assert assemble and assemble[-1].get("mode") == "self"
