import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, send_file
)
from werkzeug.security import check_password_hash, generate_password_hash
from flaviusanalytics.utils import send_text
import os, requests, json, io, base64, shutil, html
from datetime import datetime
from pytz import timezone
from PIL import Image

bp = Blueprint('results', __name__, url_prefix='/results')

race_list_filenames = ["2022-primaries.json", "2022-sen-elections.json", "2022-gov-elections.json", "2022-house-elections.json", "2022-other-elections.json"]

race_list = {}

for race_list_filename in race_list_filenames:
    with open("flaviusanalytics/static/" + race_list_filename, "r") as race_list_file:
        race_list.update(json.load(race_list_file))

def printdate(date):
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    return months[date[1]-1] + " " + str(date[2]) + ", " + str(date[0])

def standardize_county_name(string):
    if (string == "Brooklyn"):
        return "Kings"
    if (string == "Manhattan"):
        return "New York"
    if (string == "Staten Island"):
        return "Richmond"
    if (string == "Waterville"):
        return "Waterville Valley"
    if (string == "Mont Vernon"):
        return "Mt Vernon"
    return string.replace("’", "'").replace("St.", "Saint").replace(" County", "").replace(" Twp", "")
    
def compare_county_name(name1, name2):
    return name1.replace(" ", "") == name2.replace(" ", "")
    
def site_compare(site):
    if (site == "nyt"):
        return ""
    return site

@bp.route("/download")
def download_data():
    print("Downloading!")
    folder = "instance"
    shutil.make_archive("flaviusanalytics/data", "zip", folder)
    return send_file("data.zip", as_attachment = True)

@bp.route("/display/<filename>")
def display_file(filename):
    print("Display!")
    json_filename = "instance/" + filename + ".json"
    with open(json_filename, "r") as json_file:
        json_save = json.load(json_file)
    print([json.dumps(json_save, indent = 4)])
    return render_template("results/download.html", file_name = json_filename, file_content = json.dumps(json_save, indent = 4))

@bp.route("/<race_id>")
def load_race_page(race_id):
    print("Started!")
    if (race_id not in race_list):
        return render_template("error.html", message = "This race does not exist. Fawk you mean.")
    json_filename = "instance/" + race_id + ".json"
    temp_html = "<p> Loading... </p>"
    return render_template("results/results.html", candidates = race_list[race_id]["candidates"], temp_html = temp_html, title = race_list[race_id]["name"], race_id = race_id)
    
@bp.route("/get-graph", methods = ["GET", "POST"])
def get_graph():
    race_id = request.json["race_id"]
    if (race_list[race_id]["date"] < [2022, 7, 18]):
        return {"graph" : "" }
    compare = request.json["compare"]
    compare = [html.unescape(candidate) for candidate in compare]
    window_input = request.json["window_input"]
    hypo_percent = request.json["hypo_percent"]
    print("Retrieving graph from json for " + str(race_id) + " page update.")
    
    json_filename = "instance/" + race_id + ".json"
    json_history_filename = "instance/" + race_id + "-history.json"
    with open(json_filename, "r") as json_file:
        json_save = json.load(json_file)
    if (not json_save):
        return {"graph" : "No sites available yet"}
    with open(json_history_filename, "r") as json_history_file:
        json_history_save = json.load(json_history_file)
    
    margin_over_time_graph = calculate_margin_over_time_graph(race_id, json_save["data"], json_history_save, window_input, compare, hypo_percent)
    
    return {"graph" : format_graph(race_id, margin_over_time_graph), "history" : format_history(race_id, json_history_save, compare)}

@bp.route("/get-content", methods = ["GET", "POST"])
def get_content():
    race_id = request.json["race_id"]
    compare = request.json["compare"]
    compare = [html.unescape(candidate) for candidate in compare]
    print("Retrieving data from json for " + str(race_id) + " page update.")
    
    json_filename = "instance/" + race_id + ".json"
    with open(json_filename, "r") as json_file:
        json_save = json.load(json_file)
    if (not json_save):
        return "No sites available yet"
    
    results_with_margins = calculate_margins(race_id, json_save["data"], compare)
    (county_winners, formatted_results) = format_data(race_id, results_with_margins)
    
    consolidata = {"data" : formatted_results, "sources" : json_save["sources"], "labels": json_save["labels"], "county_winners" : county_winners}
    return format_html(race_id, consolidata)

def fetch_and_update(): # Only called from fetch_timer in __init__.py
    for race_id in race_list:
        try:
            if (race_list[race_id]["when"] != "current"):
                continue
            print("Fetching for " + race_id)
            json_filename = "instance/" + race_id + ".json"
            json_history_filename = "instance/" + race_id + "-history.json"
            if (not os.path.exists(json_filename)):
                with open(json_filename, "w") as json_file:
                    json.dump({}, json_file, indent = 4)
            if (not os.path.exists(json_history_filename)):
                with open(json_history_filename, "w") as json_history_file:
                    json.dump({}, json_history_file, indent = 4)
            candidates = race_list[race_id]["candidates"]
            get_results = {"sos" : get_results_sos, "nyt" : get_results_nyt, "cnn" : get_results_cnn, "ddhq" : get_results_ddhq, "ddhq2" : get_results_ddhq2, "bg" : get_results_bg}
            data = {}
            for site in race_list[race_id]["sites"]:
                try:
                    data[site] = get_results[site](race_id)
                except json.decoder.JSONDecodeError as e:
                    print(race_id + " - Failed to find " + str(site) + " data.")
                # except:
                    # pass
            if (not data):
                print(race_id + " - No websites are even up yet. Patience, my friend!")
                with open(json_filename, "w") as json_file:
                    json.dump({}, open(json_filename, "w"), indent = 4)
                continue
            #print(data)
            sources = ", ".join(data.keys())
            (labels, aggregate_data) = aggregate(race_id, data)
            json_save = {"data" : aggregate_data, "sources" : sources, "labels": labels}
            with open(json_filename, "r") as json_file:
                last_json_save = json.load(json_file)
            changes = {}
            notify = False
            if (last_json_save):
                assert len(aggregate_data) == len(last_json_save["data"]), "Inconsistent County Lists"
                for county in range(len(aggregate_data)):
                    assert (aggregate_data[county]["county_name"].lower().replace(" ", "") == last_json_save["data"][county]["county_name"].lower().replace(" ", "") or "Saint Louis" in aggregate_data[county]["county_name"]), "Inconsistent County Lists" + str(aggregate_data[county]["county_name"]) + " does not match " + str(last_json_save["data"][county]["county_name"]) + " from " + site
                    county_changes = {}
                    for candidate in candidates:
                        county_changes[candidate] = aggregate_data[county][candidate] - last_json_save["data"][county][candidate]
                        if (county_changes[candidate] != 0):
                            notify = True
                    county_changes["total"] = aggregate_data[county]["total"] - last_json_save["data"][county]["total"]
                    if ("min_turnout" in aggregate_data[county]):
                        county_changes["min_turnout"] = aggregate_data[county]["min_turnout"] - last_json_save["data"][county].setdefault("min_turnout", 0)
                    if ("max_turnout" in aggregate_data[county]):
                        county_changes["max_turnout"] = aggregate_data[county]["max_turnout"] - last_json_save["data"][county].setdefault("max_turnout", 0)
                    if (not all(change == 0 for change in county_changes.values())):
                        county_changes["county_name"] = aggregate_data[county]["county_name"]
                        changes[county] = county_changes
            else:
                changes = dict(zip(list(range(0, len(aggregate_data))), aggregate_data))
            if (changes):
                current_time = datetime.now(timezone("America/New_York")).isoformat(timespec="seconds")
                print(race_id + " Update! " + str(current_time))
                with open(json_history_filename, "r") as json_history_file:
                    history = json.load(json_history_file)
                history[current_time] = changes
                with open(json_filename, "w") as json_file, open(json_history_filename, "w") as json_history_file:
                    json.dump(json_save, json_file, indent = 4)
                    json.dump(history, json_history_file, indent = 4)
                if (race_list[race_id]["notify"] == "True" and notify):
                    send_text(race_list[race_id]["name"] + " Update!")
            elif (sources != last_json_save["sources"] or labels != last_json_save["labels"]):
                print(race_id + " Source Update!")
                with open(json_filename, "w") as json_file:
                    json.dump(json_save, json_file, indent = 4)
            else:
                print(race_id + " - No changes since last fetching.")
        except requests.exceptions.ConnectionError:
            print(race_id + " - Failed to fetch " + str(site) + " data.")
            #send_text("Failed to fetch " + str(site) + " data in " + race_id)
        except Exception as e:
            send_text("ERROR! in " + race_id)
            print(e)
            raise e
            

def get_results_sos(race_id):
    assert ("sos" in race_list[race_id]["sites"]), "DNE"
    data = json.loads(requests.get(race_list[race_id]["sites"]["sos"]).text)
    results = []
    for county_data in data:
        if (not results or not compare_county_name(standardize_county_name(county_data["CountyName"]), results[-1][0])):
            results.append([standardize_county_name(county_data["CountyName"])] + [None] * (len(race_list[race_id]["candidates"]) + 2))
        for c in range(len(race_list[race_id]["candidates"])):
            if (race_list[race_id]["candidates"][c] in county_data["ChoiceName"]):
                results[-1][c + 1] = county_data["ChoiceTotalVotes"]
                results[-1][len(race_list[race_id]["candidates"]) + 1] = county_data["ContestTotalVotes"]
    results = [row for row in results if row[1] != None]
    results.sort()
    return results

def get_results_nyt(race_id):
    assert ("nyt" in race_list[race_id]["sites"]), "DNE"
    (url, index) = tuple(race_list[race_id]["sites"]["nyt"])
    data = json.loads(requests.get(url).text)["races"][index]
    results = []
    for county_data in data["reporting_units"]:
        if ("division" not in race_list[race_id] and county_data["level"] != "county" or "division" in race_list[race_id] and race_list[race_id]["division"] == "township" and county_data["level"] != "township"):
            continue
        if ("Location" in county_data["name"] or "Albany Township" in county_data["name"] or "Aroostook Cty" in county_data["name"]):
            continue
        row = []
        row.append(standardize_county_name(county_data["name"]))
        for candidate in race_list[race_id]["candidates"]:
            for nyt_candidate in county_data["candidates"]:
                nyt_id = nyt_candidate["nyt_id"]
                if (candidate in data["candidate_metadata"][nyt_id]["last_name"] or candidate == "O'Dea" and data["candidate_metadata"][nyt_id]["last_name"] == "O’Dea" or candidate == "Perez" and "Gluesenkamp" in data["candidate_metadata"][nyt_id]["last_name"]):
                    row.append(nyt_candidate["votes"]["total"])
        row.append(county_data["total_votes"])
        
        row.append(county_data["total_expected_vote"])
        results.append(row)
    results.sort()
    return results

def get_results_bg(race_id):
    assert ("bg" in race_list[race_id]["sites"]), "DNE"
    url = race_list[race_id]["sites"]["bg"]
    data = json.loads(requests.get(url).text)["races"][0]
    results = []
    for county_data in data["reportingUnits"]:
        if (county_data["level"] != "subunit"):
            continue
        row = []
        row.append(standardize_county_name(county_data["reportingunitName"]))
        totalvotes = 0
        for candidate in race_list[race_id]["candidates"]:
            for bg_candidate in county_data["candidates"]:
                if (candidate in bg_candidate["last"]):
                    row.append(bg_candidate["voteCount"])
                    totalvotes += bg_candidate["voteCount"]
        row.append(totalvotes)
        row.append(None)
        results.append(row)
    results.sort()
    return results

def get_results_cnn(race_id):
    candidates = race_list[race_id]["candidates"]
    assert ("cnn" in race_list[race_id]["sites"]), "DNE"
    data = json.loads(requests.get(race_list[race_id]["sites"]["cnn"]).text)
    results = []
    for county_data in data:
        if ("Location" in county_data["countyName"] or "Aroostook Cty" in county_data["countyName"]):
            continue
        row = []
        row.append(standardize_county_name(county_data["countyName"]))
        for candidate in candidates:
            for cnn_candidate in county_data["candidates"]:
                if candidate in cnn_candidate["lastName"]:
                    row.append(cnn_candidate["voteNum"])
        total = 0
        for cnn_candidate in county_data["candidates"]:
            total += cnn_candidate["voteNum"]
        row.append(total)
        if (county_data["percentReporting"] == 0):
            row.append(None)
        else:
            row.append(int(total / county_data["percentReporting"] * 100.0))
        results.append(row)
    results.sort()
    if ("-ak-" in race_id):
        totals = ["Alaska"] + len(candidates) * [0] + [0, 0]
        for row in results:
            for i in range(1, len(row)):
                if (row[i] != None):
                    totals[i] += row[i]
        return [totals]
    return results
    
def get_results_ddhq(race_id):
    assert ("ddhq" in race_list[race_id]["sites"]), "DNE"
    (url, ddhqids) = race_list[race_id]["sites"]["ddhq"]
    data = json.loads(requests.get(url).text)
    results = []
    if ("division" in race_list[race_id] and race_list[race_id]["division"] == "township"):
        for county_data in data["vcuResults"]["counties"]:
            for vcu_data in county_data["vcus"]:
                results.append([])
                results[-1].append(standardize_county_name(vcu_data["vcu"]))
                for candidate in race_list[race_id]["candidates"]:
                    results[-1].append(vcu_data["votes"][ddhqids[candidate]])
                total = 0
                for ddhq_candidate in vcu_data["votes"]:
                    total += vcu_data["votes"][ddhq_candidate]
                results[-1].append(total)
                results[-1].append(vcu_data["estimated_votes"]["estimated_votes_mid"])
        results.sort()
    else:
        for county_data in data["countyResults"]["counties"]:
            results.append([])
            results[-1].append(standardize_county_name(county_data["county"]))
            for candidate in race_list[race_id]["candidates"]:
                results[-1].append(county_data["votes"][ddhqids[candidate]])
            total = 0
            for ddhq_candidate in county_data["votes"]:
                total += county_data["votes"][ddhq_candidate]
            results[-1].append(total)
            results[-1].append(county_data["estimated_votes"]["estimated_votes_mid"])
        results.sort()
    return results

def get_maricopa():
    json_filename = "instance/maricopa.json"
    if (not os.path.exists(json_filename)):
        with open(json_filename, "w") as json_file:
            json.dump({}, json_file, indent = 4)
    print("Fetching Maricopa")
    url = "https://elections.maricopa.gov/.rest/electionresults?_t=1668296371174"
    print(requests.get(url).text)
    data = json.loads(requests.get(url).text)
    results = {}
    azgovdata = data["results"]["contestResults"][0]
    results["Hobbs"] = azgovdata["candidates"][0]["totalVotes"]
    results["Lake"] = azgovdata["candidates"][1]["totalVotes"]
    results["Total"] = azgovdata["ballotsCast"]
    hobbslead = round(((float)(results["Hobbs"] - results["Lake"]))(results["Total"]) * 100.0, 2)
    with open(json_filename, "r") as json_file:
        last_json_save = json.load(json_file)
    if (last_json_save != json_save):
        print("MARICOPA UPDATE: " + hobbslead + "%")
        send_text("MARICOPA UPDATE: " + hobbslead + "%")
        with open(json_filename, "w") as json_file:
            json.dump(json_save, json_file, indent = 4)
        
    
def get_results_ddhq2(race_id):
    assert ("ddhq2" in race_list[race_id]["sites"]), "DNE"
    (url, ddhqids) = race_list[race_id]["sites"]["ddhq2"]
    print(url)
    data = json.loads(requests.get(url).text)["data"]
    print(requests.get(url))
    results = []
    for ddhq_race in data:
        if (str(ddhq_race["race_id"]) != ddhqids["ddhq_id"]):
            continue
        for county_data in ddhq_race["vcuResults"]["counties"]:
            results.append([])
            results[-1].append(standardize_county_name(county_data["county"]))
            for candidate in race_list[race_id]["candidates"]:
                results[-1].append(county_data["votes"][ddhqids[candidate]])
            total = 0
            for ddhq_candidate in county_data["votes"]:
                total += county_data["votes"][ddhq_candidate]
            results[-1].append(total)
            results[-1].append(county_data["estimated_votes"]["estimated_votes_mid"])
    results.sort()
    return results

def aggregate(race_id, data):
    num_counties = -1
    for site in data:
        #print(data[site].keys())
        #assert (num_counties == -1 or num_counties == len(data[site])), "Inconsistent County Lists"
        num_counties = len(data[site])
    candidates = race_list[race_id]["candidates"]
    data_total_index = len(candidates) + 1
    data_turnout_index = len(candidates) + 2
    results = [{"county_name" : "Total"}]
    labels = {"Total" : {"main" : "nyt"}}
    for county in range(num_counties):
        county_name = ""
        for site in data:
            if (county_name == ""):
                county_name = data[site][county][0]
            else:
                assert (county_name.lower().replace(" ", "") == data[site][county][0].lower().replace(" ", "") or "Saint Louis" in county_name), "Inconsistent County Lists: " + str(county_name) + " does not match " + str(data[site][county][0]) + " from " + site
            
        results.append({})
        results[-1]["county_name"] = county_name
        labels[county_name] = {}
        for site in sorted(list(data.keys()), key = site_compare):
            if ("main" not in labels[county_name] or data[site][county][data_total_index] > data[labels[county_name]["main"]][county][data_total_index]):
                labels[county_name]["main"] = site
            site_exp_turnout = data[site][county][data_turnout_index]
            if (site_exp_turnout == None):
                continue
            if ("min" not in labels[county_name] or site_exp_turnout < data[labels[county_name]["min"]][county][data_turnout_index]):
                labels[county_name]["min"] = site
            if ("max" not in labels[county_name] or site_exp_turnout > data[labels[county_name]["max"]][county][data_turnout_index]):
                labels[county_name]["max"] = site
        for c in range(len(candidates)):
            results[-1][candidates[c]] = data[labels[county_name]["main"]][county][c + 1]
            results[0][candidates[c]] = results[0].setdefault(candidates[c], 0) + results[-1][candidates[c]]
        total = data[labels[county_name]["main"]][county][data_total_index]
        results[-1]["total"] = total
        results[0]["total"] = results[0].setdefault("total", 0) + results[-1]["total"]
        # mail = [1338, 14619, 22287, 30096, 2946, 481, 4273, 1743, 5268, 907, 8956, 471, 6198, 11689, 872, 29159, 28691, 1165, 2459, 400, 1602, 3392, 2161, 1505]
        # exp_turnout_min = total + mail[c]
        if ("min" not in labels[county_name]):
            continue
        min_turnout = data[labels[county_name]["min"]][county][data_turnout_index]
        max_turnout = data[labels[county_name]["max"]][county][data_turnout_index]
        if (total > min_turnout):
            labels[county_name]["min"] = labels[county_name]["main"]
            min_turnout = total
        if (total > max_turnout):
            labels[county_name]["max"] = labels[county_name]["main"]
            max_turnout = total
        results[-1]["min_turnout"] = min_turnout
        results[-1]["max_turnout"] = max_turnout
        results[0]["min_turnout"] = results[0].setdefault("min_turnout", 0) + results[-1]["min_turnout"]
        results[0]["max_turnout"] = results[0].setdefault("max_turnout", 0) + results[-1]["max_turnout"]
    return (labels, results)

def calculate_margins(race_id, data, compare):
    candidates = race_list[race_id]["candidates"]
    for county in range(1, len(data)):
        current_margin = data[county][compare[0]] - data[county][compare[1]]
        data[county]["current_margin"] = current_margin
        data[0]["current_margin"] = data[0].setdefault("current_margin", 0) + data[county]["current_margin"]
        if ("min_turnout" not in data[county]):
            continue
        if (data[county]["total"] != 0):
            exp_margin_min_turnout = int(current_margin * data[county]["min_turnout"] / data[county]["total"])
            exp_margin_max_turnout = int(current_margin * data[county]["max_turnout"] / data[county]["total"])
        else:
            exp_margin_min_turnout = 0
            exp_margin_max_turnout = 0
        data[county]["exp_margin_min_turnout"] = exp_margin_min_turnout
        data[county]["exp_margin_max_turnout"] = exp_margin_max_turnout
        data[0]["exp_margin_min_turnout"] = data[0].setdefault("exp_margin_min_turnout", 0) + data[county]["exp_margin_min_turnout"]
        data[0]["exp_margin_max_turnout"] = data[0].setdefault("exp_margin_max_turnout", 0) + data[county]["exp_margin_max_turnout"]
    return data

def encode_graph():
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.clf()
    image_encoding = base64.b64encode(buf.getvalue())
    return str(image_encoding.decode("utf-8"))

def calculate_margin_over_time_graph(race_id, data, history, window_input, compare, hypo_percent):
    candidates = race_list[race_id]["candidates"]
    points_total = [0]
    points_margin = [0]
    window = [0, 10000, -200, 200]
    if ("max_turnout" in data[0]):
        window[1] = max(window[1], int(1.2 * int(data[0]["max_turnout"])))
    for time in history:
        margin = history[time]["0"][compare[0]] - history[time]["0"][compare[1]]
        total = history[time]["0"]["total"]
        points_total.append(points_total[-1] + total)
        points_margin.append(points_margin[-1] + margin)
        window[3] = max(window[3], int(1.2 * points_margin[-1]))
        window[2] = min(window[2], int(1.2 * points_margin[-1]))
    plt.plot(points_total, points_margin, markersize=4, marker='o', color = "k")
    plt.plot(points_total[-1], points_margin[-1], marker='o', color = "g")
    for w in range(4):
        try:
            window[w] = float(window_input[w])
        except ValueError:
            pass
    if ("graph-percents" in race_list[race_id]):
        for percent in race_list[race_id]["graph-percents"]:
            final_margin = percent / 100.0 * data[0]["max_turnout"]
            plt.plot([0, data[0]["max_turnout"]], [0, final_margin], color = "purple", linestyle = "dashed", linewidth = 0.5)
            if (window[2] < final_margin and final_margin < window[3]):
                plt.text(data[0]["max_turnout"], final_margin, str(percent) + "%")
    if ("min_turnout" in data[0]):
        plt.vlines(x = data[0]["min_turnout"], ymin = window[2], ymax = window[3], colors = "green", linestyle = "dashed")
        plt.vlines(x = data[0]["max_turnout"], ymin = window[2], ymax = window[3], colors = "red", linestyle = "dashed")
    try:
        hypo_percent = float(hypo_percent)/100.0
        if (abs(hypo_percent) < 1.0):
            final_margin = points_margin[-1] + hypo_percent * (window[1] - points_total[-1])
            plt.plot([points_total[-1], window[1]], [points_margin[-1], final_margin], marker = 'o', color = "0.5", linestyle = "dashed")
    except ValueError:
        pass
    plt.xlim(window[0:2])
    plt.ylim(window[2:4])
    plt.title(compare[0] + " - " + compare[1] + " Margin")
    print(compare[0] + " - " + compare[1] + " Margin")
    plt.xlabel("Votes In")
    plt.ylabel("Margin")
    plt.rcParams["font.family"] = "Courier New"
    return encode_graph()

def format_data(race_id, aggregate_data):
    candidates = race_list[race_id]["candidates"]
    county_winners = {}
    for row in aggregate_data:
        county_winner = None
        for candidate in candidates:
            if (row[candidate] != 0 and (county_winner == None or row[candidate] > row[county_winner])):
                county_winner = candidate
        county_winners[row["county_name"]] = county_winner
        if (row["total"] != 0):
            for candidate in candidates:
                row[candidate] = str(row[candidate]) + str("\n(") + str(round(row[candidate] / row["total"] * 100.0, 2)) + str("%)")
            row["current_margin"] = str(row["current_margin"]) + str("\n(") + str(round(row["current_margin"] / row["total"] * 100.0, 2)) + str("%)")
            if ("min_turnout" in row):
                row["exp_margin_min_turnout"] = str(row["exp_margin_min_turnout"]) + str("\n(") + str(round(row["exp_margin_min_turnout"] / row["min_turnout"] * 100.0, 2)) + str("%)")
                row["exp_margin_max_turnout"] = str(row["exp_margin_max_turnout"]) + str("\n(") + str(round(row["exp_margin_max_turnout"] / row["max_turnout"] * 100.0, 2)) + str("%)")
        else:
            for candidate in candidates:
                row[candidate] = str(row[candidate])
            if ("min_turnout" in row):
                row["exp_margin_min_turnout"] = "0"
                row["exp_margin_max_turnout"] = "0"
        row["total"] = str(row["total"])
        row["current_margin"] = str(row["current_margin"])
        if ("min_turnout" in row):
            row["min_turnout"] = str(row["min_turnout"])
            row["max_turnout"] = str(row["max_turnout"])
        else:
            row["min_turnout"] = "N/A"
            row["max_turnout"] = "N/A"
            row["exp_margin_min_turnout"] = "N/A"
            row["exp_margin_max_turnout"] = "N/A"
    return (county_winners, aggregate_data)
    
def format_html(race_id, consolidata):
    html = ""
    sources = consolidata["sources"]
    html += "<p>Source(s): " + str(sources) + "</p>"
    html += format_table_html(race_id, consolidata)
    return html

def format_graph(race_id, margin_over_time_graph):
    html = ""
    html += "<img style=\"max-height:100%\"src=\"data:image/jpeg;base64," + margin_over_time_graph + "\">"
    return html

def format_history(race_id, history, compare):
    html = ""
    candidates = race_list[race_id]["candidates"]
    header = ["Time"] + candidates + ["Total", "Margin", "Percent"]
    html += "<div class=\"scroller\">"
    html += "<table>"
    html += "<tr>"
    html += "<th class=\"history-cell\" style=\"text-align:left\">" + header[0] + "</th>"
    for h in header[1:]:
        html += "<th class=\"history-cell\">" + h + "</th>"
    html += "</tr>"
    for time in list(reversed(history.keys())):
        row_html = ""
        row_html += "<tr>"
        dt = datetime.fromisoformat(time).strftime("%m/%d %H:%M")
        row_html += "<td class=\"history-cell\">" + dt + "</td>"
        empty = True;
        for candidate in candidates:
            if (history[time]["0"][candidate] != 0):
                empty = False
            row_html += "<td class=\"history-cell\"><p>" + str(history[time]["0"][candidate]) + "</td>"
        if (history[time]["0"]["total"] != 0):
            empty = False
        row_html += "<td class=\"history-cell\"><p>" + str(history[time]["0"]["total"]) + "</td>"
        margin = history[time]["0"][compare[0]] - history[time]["0"][compare[1]]
        row_html += "<td class=\"history-cell\"><p>" + str(margin) + "</td>"
        if (history[time]["0"]["total"] != 0):
            row_html += "<td class=\"history-cell\">" + str(round(margin / history[time]["0"]["total"] * 100.0, 2)) + "%</td>"
        row_html += "</tr>"
        if (not empty):
            html += row_html
    html += "</table>"
    html += "</div>"
    return html

def format_table_html(race_id, consolidata):
    html = ""
    candidates = race_list[race_id]["candidates"]
    header = ["County"] + candidates + ["Total", "Current Margin", "Min Turnout", "Max Turnout", "Min Turnout Margin", "Max Turnout Margin"]
    data = consolidata["data"]
    
    labels = consolidata["labels"]
    county_winners = consolidata["county_winners"]
    #print(labels)
    
    html += "<table>"
    html += "<tr>"
    html += "<th class=\"results-table\" style=\"text-align:left\">" + header[0] + "</th>"
    for h in header[1:]:
        html += "<th>" + h + "</th>"
    html += "</tr>"
    for row in data:
        if (row["county_name"] == "Total"):
            html += "<tr style=\"font-weight:bolder\">"
        else:
            html += "<tr>"
        html += "<td class=" + labels[row["county_name"]]["main"] + " style=\"text-align:left\"><p>" + row["county_name"] + "</p></td>"
        for candidate in candidates:
            html += "<td class=" + labels[row["county_name"]]["main"]
            if (candidate == county_winners[row["county_name"]]):
                html += " style=\"background-color: #00ff00\""
            html += "><p>" + row[candidate] + "</p></td>"
        html += "<td class=" + labels[row["county_name"]]["main"] + "><p>" + row["total"] + "</p></td>"
        html += "<td class=" + labels[row["county_name"]]["main"] + "><p>" + row["current_margin"] + "</p></td>"
        html += "<td class=" + labels[row["county_name"]].setdefault("min", "nyt") + "><p>" + row["min_turnout"] + "</p></td>"
        html += "<td class=" + labels[row["county_name"]].setdefault("max", "nyt") + "><p>" + row["max_turnout"] + "</p></td>"
        html += "<td class=" + labels[row["county_name"]].setdefault("min", "nyt") + "><p>" + row["exp_margin_min_turnout"] + "</p></td>"
        html += "<td class=" + labels[row["county_name"]].setdefault("max", "nyt") + "><p>" + row["exp_margin_max_turnout"] + "</p></td>"
        html += "</tr>"
    html += "</table>"
    return html
