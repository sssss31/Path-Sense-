from app.services.confidence import confidence_for
def test_live_sources_have_higher_confidence_than_missing_sources():
    live={k:{"status":"live"} for k in ["routing","weather","terrain","landslide","road_condition"]};partial={**live,"weather":{"status":"unavailable"},"road_condition":{"status":"estimated"}}
    assert confidence_for(live)[0]>confidence_for(partial)[0]
def test_confidence_does_not_modify_accessibility_score():
    low,_=confidence_for({});assert low==0
