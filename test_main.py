import unittest
import main
import mock

class EstimateTestTimesTestCase(unittest.TestCase):
    def setUp(self):
        self.ett = main.EstimateTestTimes()

    def start_ptt_test(self, time_str, test_name):
        self.ett.process_line("[2016-08-30 {}] [INFO] [default] automated-testing-test-start [TCU][run][2016-08-30-17-42-14][{}]".format(time_str, test_name))

    def end_ptt_test(self, time_str, test_name):
        self.ett.process_line("[2016-08-30 {}] [INFO] [default] automated-testing-test-done [TCU][run][2016-08-30-17-42-14][{}]".format(time_str, test_name))

    def test_single_test_duration(self):
        self.start_ptt_test("19:01:57.500", "0052_PTT_ServoVoltage")
        self.end_ptt_test("19:02:58.750", "0052_PTT_ServoVoltage")

        assert "0052_PTT_ServoVoltage" in self.ett.time_data
        self.assertEqual(61.25, self.ett.time_data["0052_PTT_ServoVoltage"][0].duration)

    def test_multiple_test_duration(self):
        self.start_ptt_test("19:01:57.500", "0052_PTT_ServoVoltage")
        self.end_ptt_test("19:02:58.750", "0052_PTT_ServoVoltage")

        self.start_ptt_test("19:01:57.500", "0053_PTT_ChuckNorris")
        self.end_ptt_test("19:02:59.750", "0053_PTT_ChuckNorris")

        assert "0052_PTT_ServoVoltage" in self.ett.time_data
        assert "0053_PTT_ChuckNorris" in self.ett.time_data

    def test_test_is_rejected_when_duration_is_small(self):
        self.start_ptt_test("19:01:57.500", "0053_PTT_test")
        self.end_ptt_test("19:01:57.750", "0053_PTT_test")
        assert "0052_PTT_ServoVoltage" not in self.ett.time_data

    def test_ignores_incomplete_start_tags(self):
        self.ett.process_line("[2016-08-30 10:33:51.228] [INFO] [default] automated-testing-test-start [TCU][prepare][2016-08-30-10-33-49]")
        self.end_ptt_test("19:01:57.750", "0053_PTT_test")
        assert not self.ett.time_data

    def test_ignores_incomplete_end_tags(self):
        self.start_ptt_test("19:01:57.750", "0053_PTT_test")
        self.ett.process_line("[2016-08-30 10:33:51.228] [INFO] [default] automated-testing-test-start [TCU][restore][2016-08-30-10-33-49]")
        assert not self.ett.time_data

    def test_updates_measurement_analysis(self):
        mock_analysis = mock.MagicMock()
        with mock.patch("main.EstimateMeasurementTimes", return_value=mock_analysis):
            self.start_ptt_test("19:01:57.500", "0053_PTT_test")
            self.ett.process_line("Someline")
            mock_analysis.process_line.assert_called_with("Someline")

    def test_resets_measurement_analysis_on_every_test_start(self):
        with mock.patch("main.EstimateMeasurementTimes") as mock_analysis:
            self.start_ptt_test("19:01:57.500", "0053_PTT_test")
            assert mock_analysis.called
            self.end_ptt_test("19:01:57.500", "0053_PTT_test")

            mock_analysis.reset_mock()
            self.start_ptt_test("19:01:57.500", "0053_PTT_test")
            assert mock_analysis.called
            self.end_ptt_test("19:01:57.500", "0053_PTT_test")

    def test_adds_measurement_analysis_to_test_record(self):
        mock_analysis = mock.MagicMock()
        mock_analysis.get_data.return_value = "AnalysisData"
        mock_analysis.total_sleep = 123.456

        with mock.patch("main.EstimateMeasurementTimes", return_value=mock_analysis):
            self.start_ptt_test("19:01:57.500", "0053_PTT_test")
            self.end_ptt_test("19:05:57.500", "0053_PTT_test")
            self.assertEqual("AnalysisData", self.ett.time_data["0053_PTT_test"][0].measurement_times)
            self.assertEqual(123.456, self.ett.time_data["0053_PTT_test"][0].total_sleep)

class EstimateMeasurementTimesTestCase(unittest.TestCase):
    def setUp(self):
        self.emt = main.EstimateMeasurementTimes()

    def do_measurement(self, mode, measurement_time):
        def get_time(increment):
            hh, mm, ss = (10, 40, 0.0)
            ss += increment
            if ss >= 60.0:
                ss -= 60.0
                mm += 1

            return hh, mm, ss

        if mode == "FREQUENCY":
            config_command = "CONFigure:FREQuency AUTO,DEF,(@318)"
        else:
            config_command = "CONFigure:VOLTage:{} AUTO,DEF,(@318)".format(mode)

        h, m, s = get_time(0)
        self.emt.process_line("[2016-08-30 {}:{}:{:.3f}] [DEBUG] [Rigol-M300] WRITING COMMAND: '{}' (delay was 1211 ms, slept 0 ms).".format(h,m,s, config_command))

        h, m, s = get_time(measurement_time)
        self.emt.process_line("[2016-08-30 {}:{}:{:.3f}] [DEBUG] [Rigol-M300] Response for SYSTEM:ERROR? for command FETCh?: +0,\"No error\" (processing time 0 ms).".format(h,m,s))

        h, m, s = get_time(measurement_time + 1)
        self.emt.process_line("[2016-08-30 {}:{}:{:.3f}] [DEBUG] [Rigol-M300] WRITING COMMAND: '{}' (delay was 1211 ms, slept 0 ms).".format(h,m,s, config_command))

    def test_measures_initialization_time(self):
        self.emt.process_line("[2016-08-30 10:39:00.000] [DEBUG] [Rigol-M300] WRITING COMMAND: '*RST' (delay was 1000 ms, slept 0 ms).")
        self.emt.process_line("[2016-08-30 10:40:00.000] [DEBUG] [Rigol-M300] WRITING COMMAND: 'CONFigure:VOLTage:DC AUTO,DEF,(@318)' (delay was 1211 ms, slept 0 ms).")
        self.assertEqual(60.0, self.emt.get_data()["INITIALIZATION"][0])

    def test_measures_dc_measurement_time(self):
        self.do_measurement("DC", 90.0)
        self.assertEqual(90.0, self.emt.get_data()["DC"][0])

    def test_measures_ac_measurement_time(self):
        self.do_measurement("AC", 90.0)
        self.assertEqual(90.0, self.emt.get_data()["AC"][0])

    def test_measures_frequency_measurement_time(self):
        self.do_measurement("FREQUENCY", 90.0)
        self.assertEqual(90.0, self.emt.get_data()["FREQUENCY"][0])

    def test_measurement_time_is_measured_between_configure_and_last_fetch(self):
        self.emt.process_line("[2016-08-30 10:40:00.000] [DEBUG] [Rigol-M300] WRITING COMMAND: 'CONFigure:VOLTage:AC AUTO,DEF,(@318)' (delay was 1211 ms, slept 0 ms).")
        self.emt.process_line("[2016-08-30 10:40:01.000] [DEBUG] [Rigol-M300] Response for SYSTEM:ERROR? for command FETCh?: +0,\"No error\" (processing time 0 ms).")
        self.emt.process_line("[2016-08-30 10:40:01.500] [DEBUG] [Rigol-M300] Response for SYSTEM:ERROR? for command FETCh?: +0,\"No error\" (processing time 0 ms).")
        self.emt.process_line("[2016-08-30 10:41:30.000] [DEBUG] [Rigol-M300] WRITING COMMAND: 'CONFigure:BLAARG AUTO,DEF,(@318)' (delay was 1211 ms, slept 0 ms).")
        self.assertEqual(1.5, self.emt.get_data()["AC"][0])

    def test_sums_total_sleep_time(self):
        self.emt.process_line("(slept 100 ms).")
        self.do_measurement("FREQUENCY", 90.0)
        self.emt.process_line("(slept 500 ms).")
        self.do_measurement("FREQUENCY", 90.0)

        self.assertEqual(0.600, self.emt.total_sleep)

if __name__ == '__main__':
    unittest.main()
