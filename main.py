import re
from datetime import datetime
import time
import functools


LOGFILE = r"D:\Bugs\Rigol\smartsdkrest-2016-08-30.log"

class Base:
    TIME_RE = re.compile(r"^\[(\d+)-(\d+)-(\d+) (\d+):(\d+):(\d+)\.(\d+)\]")

    def get_time(self, line):
        m = self.TIME_RE.match(line)
        if m is None:
            raise ValueError("Invalid start time.")

        year, month, day, hour, minute, seconds, millisecond = list(map(lambda x: int(x), m.groups()))
        dt = datetime(year, month, day,hour,minute,seconds, millisecond * 1000)

        return (dt - datetime(1970, 1, 1)).total_seconds()

class TestDurationRecord:
    def __init__(self, duration, measurement_analysis):
        self.duration = duration
        self.measurement_times = measurement_analysis.get_data()
        self.total_sleep = measurement_analysis.total_sleep

class EstimateTestTimes(Base):
    NAME_RE = re.compile(r".+\[(\d+_PTT_[A-Za-z_0-9]+)\]")
    MINIMUM_TEST_TIME = 30

    def __init__(self):
        self.time_data = {}
        self.__start_time = 0
        self.__test_name = ""
        self.__measurement_analysis = None

    def __get_name(self, line):
        m = self.NAME_RE.match(line)
        if m is None:
            raise ValueError("Invalid name.")

        return m.group(1)

    def __is_sentinel(self, line, signature):
        return signature in line and\
               "[prepare]" not in line and\
               "[restore]" not in line

    def __end_test(self, duration):
        if duration < self.MINIMUM_TEST_TIME:
            return

        if self.__test_name not in self.time_data:
            self.time_data[self.__test_name] = []

        self.time_data[self.__test_name].append(TestDurationRecord(duration, self.__measurement_analysis))
        self.__start_time = 0
        self.__test_name = ""

    def process_line(self, line):
        if self.__measurement_analysis is not None:
            self.__measurement_analysis.process_line(line)

        if self.__is_sentinel(line, "automated-testing-test-start"):
            self.__start_time = self.get_time(line)
            self.__test_name = self.__get_name(line)
            self.__measurement_analysis = EstimateMeasurementTimes()
        elif self.__test_name and self.__is_sentinel(line, "automated-testing-test-done"):
            end_time = self.get_time(line)
            end_name = self.__get_name(line)
            if end_name != self.__test_name:
                raise ValueError("End name '{}' does not match start name '{}'". format(end_name, self.__test_name))

            self.__end_test(end_time - self.__start_time)

    def collect(self):
        line_number = 1
        for line in open(LOGFILE):
            try:
                self.process_line(line)
            except ValueError as e:
                print("Invalid data on line {} ({})".format(line_number, e))
                break

            line_number += 1

    def publish(self):
        for n in self.time_data:
            print("{} - {}".format(n, list(map(lambda x: x.duration, self.time_data[n]))))

            first_test = self.time_data[n][0]
            measurement_data = first_test.measurement_times
            for m in measurement_data:
                print("    {:<22s}: {}".format(m, measurement_data[m]))
            total_time = functools.reduce (lambda x, y: x + sum(measurement_data[y]), measurement_data, 0)
            print("    Total measurement time: {} (of which {:.3f} s sleeping)".format(total_time, first_test.total_sleep))
            print("")


class EstimateMeasurementTimes(Base):
    SLEEP_RE = re.compile(r".+slept (\d+) ms")

    def __init__(self):
        self.durations = {}
        self.__start = 0
        self.__state = ""
        self.__last_fetch = 0
        self.total_sleep = 0

    def __end_state(self, end):
        if not self.__state.strip():
            raise ValueError("Empty state name")

        if self.__state not in self.durations:
            self.durations[self.__state] = []

        if self.__last_fetch == 0:
            self.durations[self.__state].append(end - self.__start)
        else:
            self.durations[self.__state].append(self.__last_fetch - self.__start)

        self.__last_fetch = 0
        self.__state = ""
        self.__start = 0

    def __get_configure_state(self, line):
        state = ""

        if ":DC" in line:
            state = "DC"
        elif ":AC" in line:
            state = "AC"
        elif ":FREQuency" in line:
            state = "FREQUENCY"

        return state

    def process_line(self, line):
        if "[Rigol-M300] WRITING COMMAND: '*RST'" in line:
            self.__start = self.get_time(line)
            self.__state = "INITIALIZATION"
        elif "[Rigol-M300] WRITING COMMAND: 'CONFigure:" in line:
            line_time = self.get_time(line)
            if self.__state:
                self.__end_state(line_time)

            self.__start = line_time
            self.__state = self.__get_configure_state(line)
        elif "for command FETCh?" in line:
            self.__last_fetch = self.get_time(line)

        if "slept" in line:
            self.total_sleep += float(self.SLEEP_RE.match(line).group(1)) / 1000.0

    def collect(self):
        line_number = 1

        for line in open(LOGFILE):
            try:
                self.process_line(line)
            except ValueError as e:
                print("Invalid data on line {} ({})".format(line_number, e))
                break

            line_number += 1

    def publish(self):
        print("Mean times")
        list(map(lambda n: print("{:<45s} [{}]: {}".format(n, len(self.durations[n]), sum(self.durations[n]) / len(self.durations[n]))), self.durations))

    def get_data(self):
        return self.durations

if __name__ == "__main__":
    est = EstimateTestTimes()
    est.collect()
    est.publish()
