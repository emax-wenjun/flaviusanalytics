import json, os, requests
from flask import (
    Blueprint, render_template, request
)
from flaviusanalytics.results import race_list, fetch_and_update
from flaviusanalytics.utils import send_text
from datetime import datetime

polls_bp = Blueprint('polls', __name__, url_prefix='/polls')

def fetch_and_update_polls():
    for race_id in race_list:
        try:
            if (race_list[race_id]["when"] == "past" or "polls" not in race_list[race_id]):
                continue
            print("Fetching polls for " + race_id)
            json_polls_filename = "instance/" + race_id + "-polls.json"
            if (not os.path.exists(json_polls_filename)):
                with open(json_polls_filename, "w") as json_polls_file:
                    json.dump({}, json_polls_file, indent = 4)
            candidates = race_list[race_id]["candidates"]
            try:
                polls = get_polls(race_id)
                #print(polls)
            except json.decoder.JSONDecodeError as e:
                print(race_id + " - Failed to find data.")
            if (not polls):
                print(race_id + " - No polls are even up yet. Patience, my friend!")
                with open(json_polls_filename, "w") as json_file:
                    json.dump({}, open(json_polls_filename, "w"), indent = 4)
                continue
            with open(json_polls_filename, "r") as json_polls_file:
                prev_polls = json.load(json_polls_file)
            new_polls = []
            if (prev_polls):
                for poll in polls:
                    if poll not in prev_polls:
                        new_polls.append(poll)
            else:
                new_polls = polls
            if (new_polls):
                for poll in new_polls:
                    print(race_list[race_id]["name"] + " New Poll from " + poll["pollster"] + "!")
                    with open(json_polls_filename, "w") as json_polls_file:
                        json.dump(polls, json_polls_file, indent = 4)
                    send_text(race_list[race_id]["name"] + " New Poll from " + poll["pollster"] + "!")
            else:
                print(race_id + " - No changes since last fetching.")
        except Exception as e:
            #message = send_text("ERROR! in " + race_id)
            print(e)

def get_polls(race_id):
    assert ("polls" in race_list[race_id]), "DNE"
    candidates = race_list[race_id]["candidates"]
    data = json.loads(requests.get(race_list[race_id]["polls"]).text)
    polls = []
    for poll in data:
        row = {}
        row["pollster"] = poll["pollster"]
        row["start"] = poll["startDate"]
        row["end"] = poll["endDate"]
        row["add"] = poll["created_at"]
        hypothetical = False
        for candidate in candidates:
            for candidate538 in poll["answers"]:
                if (candidate == candidate538["choice"]):
                    row[candidate] = float(candidate538["pct"])
            if (candidate not in row):
                hypothetical = True
        if (not hypothetical):
            polls.append(row)
    return polls