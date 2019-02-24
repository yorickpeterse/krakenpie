import unittest
from time import monotonic
from kraken import Kraken, round_temperature
from liquidctl.driver.kraken_two import KrakenTwoDriver
from unittest.mock import Mock, patch


class TestRoundTemperature(unittest.TestCase):
    def test_round_temperature(self):
        self.assertEqual(round_temperature(60.2), 61)
        self.assertEqual(round_temperature(61.2), 62)
        self.assertEqual(round_temperature(62.2), 63)
        self.assertEqual(round_temperature(63.2), 65)
        self.assertEqual(round_temperature(64.2), 65)


class TestKraken(unittest.TestCase):
    def setUp(self):
        self.device = Mock(spec=KrakenTwoDriver)

        with patch('kraken._find_kraken', return_value=self.device), \
                patch('kraken._gpu_handle', return_value=42):
            self.kraken = Kraken()

    def test_status(self):
        raw_status = [
            ('Liquid temperature', '30', 'C'),
            ('Fan speed', '1500', 'RPM'),
            ('Pump speed', '1200', 'RPM'),
        ]

        with patch.object(self.device, 'get_status', return_value=raw_status):
            status = self.kraken.status()

            self.assertEqual(status['liquid'], '30')
            self.assertEqual(status['fan'], '1500')
            self.assertEqual(status['pump'], '1200')

    def test_liquid_temperature(self):
        with patch.object(self.kraken, 'status', return_value={'liquid': 33.3}):
            self.assertEqual(self.kraken.liquid_temperature(), 35)

    def test_gpu_temperature(self):
        with patch('kraken.nvmlDeviceGetTemperature', return_value=33.3):
            self.assertEqual(self.kraken.gpu_temperature(), 35)

    def test_set_speed_with_same_value(self):
        self.kraken.current['fan'] = 80

        with patch.object(self.device, 'set_fixed_speed') as set_fixed_speed:
            self.kraken.set_speed('fan', 80)
            set_fixed_speed.assert_not_called()

    def test_set_speed_with_smaller_value_without_downscaling(self):
        self.kraken.current['fan'] = 90
        self.kraken.last_update = monotonic()

        with patch.object(self.device, 'set_fixed_speed') as set_fixed_speed:
            self.kraken.set_speed('fan', 80)
            set_fixed_speed.assert_not_called()

    def test_set_speed_with_smaller_value_with_downscaling(self):
        self.kraken.current['fan'] = 90
        self.kraken.last_update = -500.0

        with patch.object(self.device, 'set_fixed_speed') as set_fixed_speed:
            self.kraken.set_speed('fan', 80)
            set_fixed_speed.assert_called_with('fan', 80)

    def test_set_speed_with_greater_value(self):
        self.kraken.current['fan'] = 50

        with patch.object(self.device, 'set_fixed_speed') as set_fixed_speed:
            self.kraken.set_speed('fan', 80)
            set_fixed_speed.assert_called_with('fan', 80)

    def test_set_speed_without_previous_value(self):
        with patch.object(self.device, 'set_fixed_speed') as set_fixed_speed:
            self.kraken.set_speed('fan', 80)
            set_fixed_speed.assert_called_with('fan', 80)
            self.assertEqual(self.kraken.current['fan'], 80)

    def test_allow_downscaling(self):
        with patch.object(self.kraken, 'last_update', monotonic()):
            self.assertFalse(self.kraken.allow_downscaling())

        with patch.object(self.kraken, 'last_update', monotonic() - 100):
            self.assertTrue(self.kraken.allow_downscaling())

    def test_apply_curve(self):
        with patch.object(self.kraken, 'set_speed') as set_speed:
            self.kraken.apply_curve(75, 'fan')
            set_speed.assert_called_with('fan', 80)


if __name__ == '__main__':
    unittest.main()
