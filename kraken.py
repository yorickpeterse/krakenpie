from liquidctl.driver.kraken_two import KrakenTwoDriver
from time import sleep, monotonic
from math import ceil
from py3nvml.py3nvml import nvmlInit, nvmlDeviceGetHandleByIndex, \
    nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU


def round_temperature(temp: float):
    """
    Rounds a temperature (in celcius) to the nearest multiple of 5, or rounds it
    up to the nearest value if the difference would be too great.

    GPU temperatures can fluctuate quite a bit. For example, instead of being
    exactly 65C a GPU core's temperature might vary between 64.0 and 65.0C.

    This method takes a temperature and rounds it to the nearest multiple of 5.
    If the difference of this value compared to the raw value is too great, we
    simply round it up. This means that a temperature of 60.5C becomes 61, and a
    temperature of 63.5C becomes 65C.
    """

    multiple_of = 5
    rounded = ceil(multiple_of * ceil(temp / multiple_of))

    if rounded - temp <= 2.0:
        return rounded
    else:
        return ceil(temp)


def _find_kraken():
    devices = KrakenTwoDriver.find_supported_devices()

    if not devices:
        raise KrakenNotFoundError('Failed to find the Kraken X')

    return devices[0]


def _gpu_handle():
    nvmlInit()

    return nvmlDeviceGetHandleByIndex(0)


class KrakenNotFoundError(Exception):
    pass


class Kraken:
    """
    Fan and pump control for the Kraken X, taking into account both the liquid
    and GPU core temperatures.
    """

    # The time (in seconds) to wait between increasing fan/pump speeds.
    CHECK_INTERVAL = 5

    # The delay between scaling the fans down.
    SCALE_DOWN_DELAY = 10

    CURVES = {
        # The GPU core temperature ranges and their corresponding fan speeds.
        'fan': {
            # The default fan speed to prevent the GPU from setting itself on
            # fire.
            range(0, 61): 50,

            # A fan speed of 60% keeps the GPU core at about 65C at 100%
            # utilisation, without being too noisy.
            range(60, 66): 60,

            # These fan speeds should in most cases only be applied when the GPU
            # is getting _really_ hot.
            range(66, 71): 65,
            range(71, 76): 80,
            range(75, 100): 100
        },
        # The Kraken liquid temperature ranges and their corresponding pump
        # speeds.
        'pump': {
            range(0, 40): 70,
            range(40, 100): 100
        }
    }

    def __init__(self):
        # The Kraken X to control.
        self.kraken = _find_kraken()

        # Handle to the nvidia GPU to read temperatures from.
        self.gpu = _gpu_handle()

        # The current speeds of the fan and the pump.
        self.current = {'fan': 0, 'pump': 0}

        # The last update to the fan/pump speeds.
        self.last_update = {'fan': monotonic(), 'pump': monotonic()}

    # Returns a dictionary containing the status details of the Kraken.
    #
    # Possible keys: fan, liquid, firmware, pump
    def status(self):
        status = {}

        for tup in self.kraken.get_status():
            status[tup[0].lower().split(' ')[0]] = tup[1]

        return status

    # Returns the temperature (in celcius) of the liquid in the kraken.
    def liquid_temperature(self):
        return round_temperature(self.status()['liquid'])

    # Returns the GPU core temperature in celcius.
    def gpu_temperature(self):
        raw_temp = nvmlDeviceGetTemperature(self.gpu, NVML_TEMPERATURE_GPU)

        return round_temperature(raw_temp)

    def set_speed(self, channel: str, new_value: int):
        current = self.current[channel]

        if new_value == current:
            self.last_update[channel] = monotonic()
            return

        if new_value < current and not self.allow_downscaling(channel):
            # To prevent the fans from scaling up and down due to small
            # temperature changes, we only allow scaling down after a certain
            # amount of time has elapsed since the last fan adjustments.
            return

        self.kraken.set_fixed_speed(channel, new_value)
        self.current[channel] = new_value
        self.last_update[channel] = monotonic()

    def allow_downscaling(self, channel):
        return monotonic() - self.last_update[channel] >= self.SCALE_DOWN_DELAY

    def apply_curve(self, current_temp: float, channel: str):
        curves = self.CURVES[channel]

        for temp_range, new_speed in curves.items():
            if current_temp in temp_range:
                self.set_speed(channel, new_speed)
                return

    def monitor(self):
        while True:
            self.apply_curve(self.gpu_temperature(), 'fan')
            self.apply_curve(self.liquid_temperature(), 'pump')

            sleep(self.CHECK_INTERVAL)


if __name__ == '__main__':
    Kraken().monitor()
