import json
from flask import (
    Blueprint, render_template, request
)
from flaviusanalytics.results import race_list, fetch_and_update
from datetime import datetime

overview_bp = Blueprint('overview', __name__)

@overview_bp.route("/")
def home():
    html = ""
    html += get_dashboard(720)
    return render_template('dashboard.html', content = html)
    
def get_summary_cell(race_id):
    html = ""
    json_filename = "instance/" + race_id + ".json"
    with open(json_filename, "r") as json_file:
        json_save = json.load(json_file)
    totals = None
    winner = None
    second = None
    margin_tag = None
    if (json_save):
        totals = json_save["data"][0]
        if (totals["total"] != 0):
            for candidate in race_list[race_id]["candidates"]:
                if (winner == None or totals[candidate] > totals[winner]):
                    second = winner
                    winner = candidate
                elif (second == None or totals[candidate] > totals[second]):
                    second = candidate
    html += "<td class=\"summary-cell\">"
    html += "<p><a href=\"results/" + race_id + "\" style=\"color: #000000; text-decoration: none; font-weight: bold\">"
    html += race_list[race_id]["name"][5:-9]
    html += "</a></p>"
    for c in range(len(race_list[race_id]["candidates"])):
        candidate = race_list[race_id]["candidates"][c]
        party_colors = { 0 : "#244999", 1 : "#D22532", 2 : "#000000" }
        if (candidate == winner):
            html += "<p style=\"background-color: #00ff00; color:" + party_colors[c] + "\">"
        else:
            html += "<p style=\"color:" + party_colors[c] + "\">"
        html += candidate
        html += "<span style=\"float:right\">"
        if (totals == None or totals["total"] == 0):
            html += "0%"
        else:
            margin_tag = "(+" + str(round((totals[winner] - totals[second]) / totals["total"] * 100.0, 1)) + "%) "
            if (candidate == winner):
                html += margin_tag
            else:
                html += " " * len(margin_tag)
            html += str(round(totals[candidate] / totals["total"] * 100.0, 1)) + "%"
        html += "</span>"
        html += "</p>"
    if (totals["min_turnout"] > 0):
        low_percent = str(round(totals["total"] / totals["max_turnout"] * 100.0))
        high_percent = str(round(totals["total"] / totals["min_turnout"] * 100.0))
        if (low_percent != high_percent):
            html += "<p>" + low_percent + "-" + high_percent + "% in</p>"
        else:
            html += "<p>" + low_percent + "% in</p>"
    html += "</td>"
    return html
    

@overview_bp.route("/get_dashboard", methods = ["GET", "POST"])
def get_dashboard(dim_x = None):
    if (dim_x == None):
        dim_x = int(request.json["dim_x"])
    html = ""
    race_times = {}
    for race_id in race_list:
        if (race_list[race_id]["date"] == [2022, 11, 8] and "time" in race_list[race_id]):
            if (race_list[race_id]["time"] in race_times):
                race_times[race_list[race_id]["time"]].append(race_id)
            else:
                race_times[race_list[race_id]["time"]] = [race_id]
    html += "<p><b>Click races for detailed results</b></p>"
    html += "<p></p>"
    for time in sorted(race_times.keys()):
        html += "<p>"
        html += str(int(time))
        if (float(time) % 1 == 0.5):
            html += ":30"
        if (int(time) == 12):
            html += " AM Poll Closings:</p>"
        else:
            html += " PM Poll Closings:</p>"
        html += "<table>"
        html += "<tr>"
        race_times[time] = sorted(race_times[time])
        races_per_row = min((dim_x - 110) // 264, 6)
        for r in range(len(race_times[time])):
            if (r > 0 and r % races_per_row == 0):
                html += "</tr><tr>"
            race_id = race_times[time][r]
            html += get_summary_cell(race_id)
        html += "</tr>"
        html += "</table>"
    return html

@overview_bp.route("/<period>")
def period_race_overview(period):
    with open("flaviusanalytics/static/" + period + ".json", "r") as race_list_file:
        period_race_list = json.load(race_list_file)
    year = period.split('-')[0]
    if ("primaries" in period):
        html = ""
        html += "<table>"
        date = [2010, 10, 10];
        for race_id in period_race_list:
            if (period_race_list[race_id]["date"] > date):
                date = period_race_list[race_id]["date"]
                html += "<p>" + str(datetime(*date).strftime("%B %d, %Y")) + " Elections:</p>"
            html += "<p><a href=results/" + race_id + ">" + period_race_list[race_id]["name"] + "</a></p>"
        html += "</table>"
        return render_template('index.html', title = year + " Primaries", content = html)
    if ("house" in period):
        html = ""
        html += "<table>"
        html += "<tr>"
        r = 0
        races_per_row = 4
        for race_id in sorted(period_race_list.keys()):
            if (r > 0 and r % races_per_row == 0):
                html += "</tr><tr>"
            html += get_summary_cell(race_id)
            r += 1
        html += "</tr>"
        html += "</table>"
        return render_template('index.html', title = year + " Primaries", content = html)
        
    seat = period.split('-')[1]
    with open("flaviusanalytics/static/" + period + "-other.json", "r") as race_list_file_other:
        period_race_list_other = json.load(race_list_file_other)
    with open("flaviusanalytics/static/map_usa.json", "r") as map_usa_file:
        map_usa = json.load(map_usa_file)
    colors = { "dark-d" : "#244999", "medium-d" : "#577CCC", "light-d" : "#8AAFFF", "light-r" : "#FF8B98", "medium-r" : "#FF5865", "dark-r" : "#D22532", "none" : "#D3D3D3" }
    html = ""
    for state in map_usa:
        race_id = year + '-' + state + '-' + seat + '-' + "election"
        if (state in period_race_list_other):
            html += "<path id=\"" + state + "\" data-info=\"<div>" + map_usa[state]["name"] + "</div><div>" + period_race_list_other[state]["name"] + "</div>\" fill=\"" + colors[period_race_list_other[state]["color"]] + "\" stroke=\"#000000\" stroke-width=\"1px\" d=\"" + map_usa[state]["shape"] + "\"/>"
        elif (race_id in period_race_list):
            html += "<a href=\"" + "results/" + race_id + "\">"
            html += "<path id=\"" + state + "\" data-info=\"<div>" + map_usa[state]["name"] + "</div><div>" + " vs. ".join(period_race_list[race_id]["candidates"]) + "</div>\" fill=\"" + colors[period_race_list[race_id]["color"]] + "\" stroke=\"#00FF00\" stroke-width=\"2px\" d=\"" + map_usa[state]["shape"] + "\"/>"
            html += "</a>"
        else:
            html += "<path id=\"" + state + "\" data-info=\"<div>" + map_usa[state]["name"] + "</div>\" fill=\"#D3D3D3\" stroke=\"#000000\" stroke-width=\"1px\" d=\"" + map_usa[state]["shape"] + "\"/>"
    title = year + ' ' + { "sen" : "Senate", "gov" : "Governor" }[seat] + ' ' + "Elections"
    return render_template("map.html", title = title, states_html = html)
    
@overview_bp.route("/error")
def error():
    error_id = request.args.get("error_id")
    message = ""
    if (error_id == "patience"):
        message = "Patience, my friend!"
    return render_template('error.html', message = message)