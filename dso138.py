#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import matplotlib
import os
import sys
from collections import namedtuple
from queue import Queue, Empty
from threading import Thread

try:
    backend = os.environ.get("MPL_BACKEND", "Qt5agg")
    matplotlib.use(backend)
    print(f"Using {backend}")
except ImportError:
    print("Using default backend")
    pass

# noinspection PyProtectedMember
from matplotlib import _pylab_helpers
from matplotlib.rcsetup import interactive_bk as _interactive_bk

import matplotlib.pyplot as plt
import serial
from matplotlib.ticker import MultipleLocator

VALUES_TO_SHOW = (
    'Vmax', 'Vmin', 'Vavr', 'Vpp', 'Freq', 'Cycl', 'PW', 'Duty'
)

queue = Queue()

sample_t = namedtuple("Sample", ["sample_no", "time", "sample"])

fig = plt.figure()
ax = fig.add_subplot()
fig.canvas.manager.set_window_title("Waiting for data...")
fig.canvas.draw()
plt.ion()
plt.show(block=False)


def mpl_pause_nostealfocus(interval, focus_figure=False):
    backend = matplotlib.rcParams['backend']
    if backend in _interactive_bk:
        figManager = _pylab_helpers.Gcf.get_active()
        if figManager is not None:
            canvas = figManager.canvas
            if canvas.figure.stale:
                canvas.draw()
            if focus_figure:
                plt.show(block=False)
            canvas.start_event_loop(interval)
            return

    # No on-screen figure is active, so sleep() is all we need.
    import time
    time.sleep(interval)


def graph_loop():
    try:
        while True:
            try:
                args = queue.get(block=False)
            except Empty:
                mpl_pause_nostealfocus(0.2)
                continue
            settings, raw_settings, samples = args

            print(f"Plotting {len(samples)} samples")
            for k, v in settings.items():
                print(f"{k}:\t{v}")

            graph(settings, raw_settings, samples)
            print("Plot completed")
    except KeyboardInterrupt:
        plt.close('all')


def graph(settings: dict, raw_settings: dict, samples: list):
    while len(fig.texts) > 0:
        del fig.texts[0]
    plt.cla()

    scaled_timebase = settings["ScaledTimebase"]
    unit = settings["TimebaseUnit"]
    divider = 1000 if unit == "ms" else 1

    fig.canvas.manager.set_window_title("Plot")
    ax.set_xlabel(unit)
    ax.set_ylabel("Volt")
    plt.subplots_adjust(left=0.1)
    ax.axis([0, samples[-1].time / divider, -4 * settings["VSen"] - settings["VPos"], 4 * settings["VSen"] - settings["VPos"]])
    ax.xaxis.set_minor_locator(MultipleLocator(scaled_timebase))
    ax.yaxis.set_major_locator(MultipleLocator(settings["VSen"]))
    ax.grid(True, which="both")
    ax.plot([0, samples[-1].time], [settings["TriggerLevel"]] * 2, ':', color="purple")

    times, volts = tuple(zip(*samples))[1:3]
    times = tuple(map(lambda x: x / divider, times))
    ax.plot(times, volts, color="orange")
    ax.set_title(f"{raw_settings.get('VSen', '')}  {raw_settings.get('Couple', '')}  "
                 f"{raw_settings.get('Timebase', '').replace('u', 'µ')}  {raw_settings.get('TriggerMode', '')}  "
                 f"{raw_settings.get('TriggerSlope')}  {raw_settings.get('TriggerLevel', '')}")

    fig_txt = ""
    for key in VALUES_TO_SHOW:
        if key in raw_settings:
            fig_txt += f"{key}: {raw_settings[key]}\n"
    fig_txt = fig_txt.strip()

    fig.text(0.01, 0.2, fig_txt, fontsize=11)

    fig.canvas.draw()
    # plt.draw_all()


def mainloop(serport: str):
    s = serial.serial_for_url(serport, baudrate=115200)
    waiting_settings = True
    settings = {
        "VPos": 0,
        "VSen": 1,
        "TriggerLevel": 0,
        "RecordLength": 0,
        "Timebase": 1
    }
    raw_settings = {}
    samples = []

    print("Waiting for data...")

    while True:
        line = s.readline()
        values = list(map(lambda x: x.strip(), line.decode().split(",")))

        if not (1 < len(values) <= 3):
            continue

        try:
            intval = int(values[0])
            if intval == 0:
                samples = []
                waiting_settings = False
                try:
                    fig.canvas.manager.set_window_title("Receiving samples...")
                except:
                    pass
                print("Receiving samples...")
            elif waiting_settings and intval > 0:
                continue
        except ValueError:
            waiting_settings = True

        if waiting_settings and len(values) != 2:
            continue

        if waiting_settings:
            setting, value = values
            raw_settings[setting] = value
            if setting not in settings.keys():
                continue
            if setting == "Timebase":
                timebase = float(value.replace("m", "").replace("u", "").replace("s", ""))
                scaled_timebase = timebase
                unit = "s"
                if value.endswith("ms"):
                    timebase /= 1000
                    unit = "ms"
                elif value.endswith("us"):
                    timebase /= 1000000
                    unit = "µs"
                settings[setting] = timebase
                settings["ScaledTimebase"] = scaled_timebase
                settings["TimebaseUnit"] = unit
            else:
                value = float(value.replace("V", ""))
                settings[setting] = value
            continue

        try:
            sample = list(map(lambda x: float(x.strip()), values))
        except ValueError:
            print("Sample reception error, please resend")
            waiting_settings = True
            continue

        sample[1] /= 1000000
        tup = sample_t(*sample)
        samples.append(tup)

        if tup.sample_no + 1 == settings["RecordLength"]:
            print(f"Received {tup.sample_no + 1} samples")
            queue.put((settings, raw_settings, samples))
            samples = []


if __name__ == '__main__':
    t = Thread(target=mainloop, args=(sys.argv[1],))
    t.start()
    graph_loop()
    t.join()
