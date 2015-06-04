from django.http import HttpResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe

import constants
import json

import pickle
import zlib
import pandas as pd
import sqlite3 as lite

from collections import OrderedDict
from django.http import HttpResponse
from bokeh.plotting import *
from bokeh.embed import autoload_server
from bokeh.models import HoverTool, TapTool, OpenURL, ColumnDataSource, Callback, GlyphRenderer


def unpickle_data(data):
    try:
        data = zlib.decompress(data)
    except:
        pass
    return pickle.loads(data)


def get_data():

    with lite.connect(constants.database_url) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT result_id, generation, result.configuration_id as conf_id, time,requestor,was_new_best, "
            " configuration.data as conf_data "
            + " FROM result "
            + " JOIN desired_result ON desired_result.result_id = result.id  "
            + " JOIN configuration ON configuration.id =  result.configuration_id  "
            + " WHERE result.state='OK' "
        )
        rows = cur.fetchall()

    cols = ["result_id", "generation", "conf_id", "time", "requestor", "was_new_best", "conf_data"]
    data = pd.DataFrame(rows, columns=cols)[["result_id", "time", "was_new_best", "conf_id", "conf_data"]]

    for i, val in enumerate(data['conf_data']):
        data['conf_data'][i] = unpickle_data(val)

    grouped = data.groupby('was_new_best')

    colors = ["red" if (val == 1) else "blue" for val in data['was_new_best'].values]

    return data, grouped.get_group(1), colors

initialized = False


def initialize_plot():
    global p, source, source_best, initialized, cur_session
    initialized = True
    data, best_data, colors = get_data()

    source = ColumnDataSource(data=dict(
        x=data['result_id'],
        y=data['time'],
        conf_id=data['conf_id'],
        conf_data=data['conf_data'],
        fill_color=colors
    ))

    source_best = ColumnDataSource(data=dict(
        x=best_data['result_id'],
        y=best_data['time'],
        conf_id=best_data['conf_id'],
        conf_data=data['conf_data']
    ))

    TOOLS = "resize,crosshair,pan,wheel_zoom,box_zoom,reset,hover,previewsave,tap"
    output_server("opentuner2")
    p = figure(
        tools=TOOLS, title="OpenTuner",
        x_axis_label='Result id', y_axis_label='time'
    )

    p.circle('x', 'y', conf_id='conf_id', fill_color='fill_color', line_color=None, source=source, size=5)
    p.line('x', 'y', conf_id='conf_id', line_color="red", source=source_best, size=5)

    callback = Callback(args=dict(source=source), code="""
        var arr = cb_obj.get('selected')['1d'].indices;
        if(arr.length > 0) {
            var data = [];
            for(var i = 0; i<arr.length; ++i) {
                data.push(cb_obj.get('data')['x'][arr[i]]);
            }
            update_conf_details(data);
        }
    """)

    taptool = p.select(dict(type=TapTool))
    taptool.action = callback

    hover = p.select(dict(type=HoverTool))
    hover.tooltips = OrderedDict([
        ("Configuration ID", "@conf_id"),
        ("Result id", "@x"),
        ("Time", "@y")
    ])
    show(p)
    cur_session = cursession()


def update_plot():
    global p, source, source_best
    data, best_data, colors = get_data()
    source.data['x'] = data['result_id']
    source.data['y'] = data['time']
    source.data['conf_id'] = data['conf_id']
    source.data['conf_data'] = data['conf_data']
    source.data['fill_color'] = colors

    source_best.data['x'] = best_data['result_id']
    source_best.data['y'] = best_data['time']
    source_best.data['conf_id'] = best_data['conf_id']
    source_best.data['conf_data'] = best_data['conf_data']

    cur_session.store_objects(source)
    cur_session.store_objects(source_best)


def get_plot_html():
    global p
    return autoload_server(p, cursession())


def index(request):
    global initialized
    if not initialized:
        initialize_plot()
    return render(request, 'plot.html', {'script_js': mark_safe(get_plot_html())})


def update(request):
    update_plot()
    return HttpResponse("success")

def config(request, point_id):
    with lite.connect(constants.database_url) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT configuration.data as conf_data "
            + " FROM result "
            + " JOIN desired_result ON desired_result.result_id = result.id  "
            + " JOIN configuration ON configuration.id =  result.configuration_id  "
            + " WHERE result.state='OK' AND result.id = '%s'" % point_id
        )
        configurations = cur.fetchone()[0]

    response_data = unpickle_data(configurations)

    return HttpResponse(json.dumps(response_data), content_type="application/json")

