import copy
import unittest

from opentelemetry.proto.common.v1.common_pb2 import AnyValue

from fidelity import any_value, check_delivery, check_projection


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.event = {'event_id': 'one', 'event_type': 'usage.recorded',
                      'time_unix_nano': '1787079590000000001', 'input_tokens': 7,
                      'cost': {'amount': .0124, 'currency': 'USD'}}
        self.observation = {'body': copy.deepcopy(self.event), 'event_name': 'usage.recorded',
                            'timestamp_ns': self.event['time_unix_nano']}

    def test_positive_projection(self):
        check_projection([self.event], [self.observation])

    def test_independent_field_changes_cannot_hide_behind_event_id(self):
        for change in ('body', 'name', 'timestamp', 'numeric_type'):
            item = copy.deepcopy(self.observation)
            if change == 'body':
                item['body']['cost']['currency'] = 'EUR'
            elif change == 'name':
                item['event_name'] = 'other'
            elif change == 'timestamp':
                item['timestamp_ns'] = str(int(item['timestamp_ns']) + 1)
            else:
                item['body']['input_tokens'] = 7.0
            with self.subTest(change=change), self.assertRaises(AssertionError):
                check_projection([self.event], [item])

    def test_empty_observations_are_not_fidelity_evidence(self):
        with self.assertRaises(AssertionError):
            check_projection([self.event], [])

    def test_nested_protobuf_values_preserve_types(self):
        value = AnyValue()
        item = value.kvlist_value.values.add(key='n')
        item.value.int_value = 7
        item = value.kvlist_value.values.add(key='flag')
        item.value.bool_value = True
        self.assertEqual(any_value(value), {'n': 7, 'flag': True})
        self.assertIs(type(any_value(value)['n']), int)
        self.assertIs(type(any_value(value)['flag']), bool)

    def test_reordered_input_preserves_events_without_transport_order_guarantee(self):
        events = [self.event, {**self.event, 'event_id': 'two',
                               'time_unix_nano': '1787079590000000000'}]
        check_delivery('reorder', events, 2, ['one', 'two'], ['one', 'two'])
        check_delivery('reorder', events, 2, ['two', 'one'], ['one', 'two'])
        with self.assertRaises(AssertionError):
            check_delivery('reorder', list(reversed(events)), 2, ['one', 'two'], ['one', 'two'])
        for evidence, attempts, commits in ((1, ['one', 'two'], ['one', 'two']),
                                            (2, ['one'], ['one', 'two']),
                                            (2, ['one'], ['one'])):
            with self.subTest(evidence=evidence, attempts=attempts, commits=commits), self.assertRaises(AssertionError):
                check_delivery('reorder', events, evidence, attempts, commits)

    def test_saturation_requires_observed_loss_with_positive_commits(self):
        events = [self.event, {**self.event, 'event_id': 'two'}]
        check_delivery('queue_saturation', events, 2, ['one'], ['one'])
        for commits in ([], ['one', 'two']):
            with self.subTest(commits=commits), self.assertRaises(AssertionError):
                check_delivery('queue_saturation', events, 2, commits, commits)
