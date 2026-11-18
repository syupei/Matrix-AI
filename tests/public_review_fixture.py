"""SIMULATED replies bound only through the consumer's public PM operations."""
import json
from practice_fixture import put


def stage_receipt(fixture, state, attention_id, person, actor='PM'):
    name = 'management/SIM-review-inputs/' + attention_id + '.json'
    put(fixture.root, name, state)
    return fixture.call('stage_confirmation', actor, state=name, attention_id=attention_id,
                        person=person)['review_receipt']
