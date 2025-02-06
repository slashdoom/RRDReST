import copy
import datetime
import json
import pytz
import re
import subprocess
import xmltodict

from collections import defaultdict
from itertools import chain


class RRD_parser:

    def __init__(self,
        rrd_file=None,
        start_time=None, end_time=None,
        epoch_output=False, timeshift=None, baseline=None
    ):
        self.rrd_file = rrd_file
        self.ds = None
        self.step = None
        if epoch_output:
            self.time_format = "%s"
        else:
            self.time_format = "%Y-%m-%d %H:%M:%S"
        self.check_dependc()
        self.start_time = start_time
        self.end_time = end_time
        self.timeshift=timeshift
        self.baseline=baseline


    def check_dependc(self):
        result = subprocess.check_output(
            "rrdtool --version",
            shell=True
        ).decode('utf-8')
        if "RRDtool 1." not in result:
            raise Exception("RRDtool version not found, check rrdtool installed")


    def get_data_source(self):
        """ gets datasources from rrd tool """

        STEP_VAL = None
        DS_VALS = []

        result = subprocess.check_output(
            f"rrdtool info {self.rrd_file}",
            shell=True
            ).decode('utf-8')

        temp_arr = result.split("\n")

        for line in temp_arr:
            if " = " in line:
                raw_key = line.split(" = ")[0]
                raw_val = line.split(" = ")[1]

            if raw_key == "step":
                STEP_VAL = raw_val

            if ("ds[" in raw_key) and ("]." in raw_key):
                match_obj = re.match(r'^ds\[(.*)\]', raw_key)
                if match_obj:
                    ds_val = match_obj.group(1)
                    if ds_val not in DS_VALS:
                        DS_VALS.append(ds_val)
        self.step = STEP_VAL
        self.ds = DS_VALS


    def get_timeshift(self, ts=None):
        """ gets timeshift from d/w/m/y format """
        if not ts:
            ts = self.timeshift
        units = {
            "s":1,
            "m":60,
            "h":3600,
            "d":86400,
            "w":604800,
            "M":2628000,
            "y":31536000,
            "Y":31536000
        }

        ts_pieces = re.findall(r"(\d+)({0})".format("|".join(units.keys())), ts)

        ts_secs = 0
        for n, u in ts_pieces:
            ts_secs += int(n) * units[u]

        return ts_secs


    def get_baseline(self, ds):
        """ Gets baseline data (mean and stddev for each baseline period) """
        timeshifts = []
        baseline_ts = re.search(r"(\d+)([dwMy])", self.baseline)

        if not baseline_ts:
            raise ValueError("Baseline timeframe must be specified (e.g., '3w', '2w').")

        baseline_number = int(baseline_ts.group(1))
        baseline_unit = baseline_ts.group(2)

        for n in range(1, (baseline_number+1)):
            timeshifts.append(str(n) + baseline_unit)

        self.timeshift = timeshifts[0]
        data = []
        for ts in timeshifts:
            data.append(self.get_rrd_json(ds, ts))

        return data


    def calculate_baseline_stats(self, data, key):
        """ Calculate the mean and standard deviation (N-1) for each baseline data series """
        depth = len(data)
        length = len(data[0]["xport"]["data"]["row"])

        if depth <= 1:
            raise ValueError("At least 2 series required for baseline.")
        if length < 1:
            raise ValueError("No data series found")

        # Create a deep copy for means and std_devs and append suffix to the legend
        means=copy.deepcopy(data[0])
        means["xport"]["meta"]["legend"]["entry"] = means["xport"]["meta"]["legend"]["entry"]+"_BASELINE_MEAN"
        std_devs=copy.deepcopy(data[0])
        std_devs["xport"]["meta"]["legend"]["entry"] = means["xport"]["meta"]["legend"]["entry"]+"_BASELINE_STDDEV"

        # Loop through each row of the data
        for l in range (0, length):
            total = 0.0  # Sum for mean
            sum_sq_diff = 0.0  # Running sum of squared differences
            mean_so_far = 0.0  # Running mean
            valid_count = 0  # Counter for valid (non-missing) values

            for d in range(depth):  # loop through each depth (each row)
                value = data[d]["xport"]["data"]["row"][l].get(key, None)  # Safely access the value with .get()

                # Skip missing values
                if value in (None, 'NaN'):
                    continue  # Skip this value and don't count it for mean or variance
                value = float(value)
                total += value
                valid_count += 1  # Increment the valid count

                # Update running mean using Welford's method
                delta = value - mean_so_far
                mean_so_far += delta / valid_count

                # Update running sum of squared differences
                sum_sq_diff += delta * (value - mean_so_far)

            # Initialize mean and std_dev to None
            mean, std_dev = None, None

            if valid_count > 1:  # If there's more than 1 valid value, calculate variance and std dev
                # Final mean after all valid values processed
                mean = total / valid_count

                # Final variance (with N-1 correction for sample variance)
                variance = sum_sq_diff / (valid_count - 1) if valid_count > 1 else 0.0

                # Standard deviation is the square root of variance
                std_dev = (variance) ** (1/2)

            del means["xport"]["data"]["row"][l][key]
            if mean is not None:
                means["xport"]["data"]["row"][l][(key+"_baseline_mean")] = str(mean)
            else:
                means["xport"]["data"]["row"][l][(key+"_baseline_mean")] = mean
            del std_devs["xport"]["data"]["row"][l][key]
            if std_dev is not None:
                std_devs["xport"]["data"]["row"][l][(key+"_baseline_stddev")] = str(std_dev)
            else:
                std_devs["xport"]["data"]["row"][l][(key+"_baseline_stddev")] = std_dev

        return means, std_devs


    def get_rrd_json(self, ds, ts=None):
        """ gets RRD json from rrd tool """
        rrd_xport_command = f"rrdtool xport --step {self.step} DEF:data={self.rrd_file}:{ds}:AVERAGE XPORT:data:{ds} --showtime"

        if self.start_time:
            ts_sec = 0
            if ts:
                ts_sec = self.get_timeshift(ts)
            start_time = self.start_time - ts_sec
            end_time = self.end_time - ts_sec
            rrd_xport_command = f"rrdtool xport DEF:data={self.rrd_file}:{ds}:AVERAGE XPORT:data:{ds} --showtime --start {start_time} --end {end_time}"
        result = subprocess.check_output(
            rrd_xport_command,
            shell=True
        ).decode('utf-8')

        json_result = json.dumps(xmltodict.parse(result), indent=4)

        # replace rrdtool v key with the ds
        replace_val = "\""+ds.lower()+"\": "
        temp_result_one = re.sub("\"v\": ",  replace_val, json_result)

        return json.loads(temp_result_one)


    def cleanup_payload(self, payload):
        """ cleans up / transforms response payload """

        # convert timezones and floats
        for count, temp_obj in enumerate(payload["data"]):
            epoch_time = temp_obj["t"]
            # Convert the epoch time to UTC
            ts = 0
            if self.timeshift:
                ts = self.get_timeshift()
            utc_time = datetime.datetime.fromtimestamp(
                int(epoch_time)+ts, tz=pytz.utc
            ).strftime(self.time_format)

            payload["data"][count]["t"] = utc_time

            for key in payload["data"][count]:
                temp_val = ""
                if payload["data"][count][key] is not None:
                    if "e+" in payload["data"][count][key] or "e-" in payload["data"][count][key]:
                        temp_val = payload["data"][count][key]
                        payload["data"][count][key] = float(temp_val)
        pl = json.dumps(payload)

        # convert ints, floats
        pl = re.sub(r'\"(\d+)\"', r'\1', f"{pl}")
        pl = re.sub(r'\"(\d+\.\d+)\"', r'\1', f"{pl}")

        # convert NaN to null
        pl = re.sub(r'\"NaN\"', "null", f"{pl}")

        # replace "t" with time
        pl = re.sub(r'\"t\"', r'"time"', f"{pl}")

        # return response as JSON obj
        return json.loads(pl)


    def compile_result(self):
        self.get_data_source()
        DS_VALUES = self.ds
        master_result = {
            "meta": {
                "start": "",
                "step": "",
                "end": "",
                "rows": "",
                "data_sources": []
            },
            "data": [],

        }

        collector = defaultdict(dict)

        for d in DS_VALUES:
            if self.baseline:
                baseline_data = self.get_baseline(d)
                means, std_devs = self.calculate_baseline_stats(baseline_data, d.lower())

                for s in (means, std_devs):
                    master_result["meta"]["start"] = datetime.datetime.fromtimestamp(
                        int(s["xport"]["meta"]["start"])
                    ).strftime(self.time_format)
                    master_result["meta"]["step"] = s["xport"]["meta"]["step"]
                    master_result["meta"]["end"] = datetime.datetime.fromtimestamp(
                        int(s["xport"]["meta"]["end"])
                    ).strftime(self.time_format)
                    master_result["meta"]["rows"] = 0
                    master_result["meta"]["data_sources"].append(
                        s["xport"]["meta"]["legend"]["entry"]
                    )

                    for collectible in chain(
                        master_result["data"], s["xport"]["data"]["row"]
                    ):
                        collector[collectible["t"]].update(collectible.items())

            r = self.get_rrd_json(ds=d, ts=self.timeshift)
            master_result["meta"]["start"] = datetime.datetime.fromtimestamp(
                int(r["xport"]["meta"]["start"])
            ).strftime(self.time_format)
            master_result["meta"]["step"] = r["xport"]["meta"]["step"]
            master_result["meta"]["end"] = datetime.datetime.fromtimestamp(
                int(r["xport"]["meta"]["end"])
            ).strftime(self.time_format)
            master_result["meta"]["rows"] = 0
            master_result["meta"]["data_sources"].append(
                r["xport"]["meta"]["legend"]["entry"]
            )

            for collectible in chain(
                master_result["data"], r["xport"]["data"]["row"]
                                    ):
                collector[collectible["t"]].update(collectible.items())

        # combine objs, add row_count
        combined_list = list(collector.values())
        master_result["data"] = combined_list
        master_result["meta"]["rows"] = len(combined_list)
        final_result = self.cleanup_payload(master_result)
        return final_result


# if __name__ == "__main__":
#     RRD_file = "sensor-voltage-cisco-entity-sensor-532.rrd"
#     rr = RRD_parser(rrd_file=RRD_file)
#     r = rr.compile_result()
#     print (r)
