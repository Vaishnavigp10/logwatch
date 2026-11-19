# Logwatch: log anomaly detection with Django

A small web app that reads application logs, groups them into one-minute windows,
finds unusual minutes with an Isolation Forest model, and explains the likely cause.

## Run it

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/

The page loads Chart.js and Google Fonts from the internet, so connect to Wi-Fi before the demo.

## Deploy to Render

1. Push this project folder to a GitHub repository.
2. In Render, choose **New + → Blueprint**, connect the repository, and deploy.
   Render reads `render.yaml` to build the app, collect static files, run database
   migrations, and generate a production `SECRET_KEY`.
3. The included free web service uses SQLite on Render's temporary filesystem.
   Its database can reset when the service restarts or redeploys. For persistent
   logs, create a Render PostgreSQL database and set the service's `DATABASE_URL`
   environment variable to its connection string; Django will use it automatically.

## Demo script (about 3 minutes)

1. Click **Load full demo**. One hour of traffic is created with an error spike and a login attack hidden in it.
2. The chart shades the flagged minutes. Open **Needs review**, then **Investigate** on one anomaly to show the probable cause and the suspicious log lines.
3. Click **Start live stream**, wait a few seconds, then click **Inject login attack** and watch a new anomaly appear.
4. Change **Sensitivity** and click **Run detection** to show how the number of alerts changes.
5. Open **Upload logs**, download the sample file, and upload it to show it works on a real file.
6. Look at the terminal where `runserver` is running: High severity anomalies print an alert email there. In the cloud design this step is Amazon SNS.

## How detection works

1. Each log line is counted into a one-minute window: total events, errors, failed logins, unique IP addresses.
2. An Isolation Forest (scikit-learn, unsupervised) marks the windows that are easiest to isolate from the rest.
3. A sanity check keeps only windows that differ clearly from the typical minute, which reduces false alarms.
4. A plain-language cause is written for each anomaly, and the engineer reviews it. The tool assists and does not replace human judgement.

## Project layout

```
config/            Django settings and root URLs
monitor/models.py  LogEntry and Anomaly tables
monitor/parser.py  Reads log lines into LogEntry objects
monitor/generator.py  Creates demo traffic
monitor/detector.py   Windows, Isolation Forest, causes, alerts
monitor/views.py   Pages and the small JSON API
monitor/templates/ and monitor/static/   User interface
sample_logs/sample.log   File to try the upload page
```

## Log line format

```
2026-11-19 10:15:32 INFO web-api 10.0.1.12 GET /cart status=200
```

## Optional: admin panel

```bash
python manage.py createsuperuser
```

Then open http://127.0.0.1:8000/admin/
