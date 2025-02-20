import os
from flask import  Flask, flash, request, redirect, url_for, render_template, Response
from flask_debugtoolbar import DebugToolbarExtension
from werkzeug.utils import secure_filename
import sqlite3
import boto3
from botocore.client import Config
from dotenv import load_dotenv

load_dotenv()

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
access_key=os.getenv('OVH_ACCESSKEY')
secret_key=os.getenv('OVH_PASSWORD')
endpoint_url=os.getenv('OVH_ENDPOINT')
bucket_name=os.getenv('OVH_BUCKET_NAME')


app = Flask(__name__)

app.config['SECRET_KEY'] = 'asdfqwerzxcv'

toolbar = DebugToolbarExtension(app)

with  sqlite3.connect('entradas.db') as db:
    cursor = db.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, eventName TEXT NOT NULL, eventDate TEXT NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT, ticketPath TEXT NOT NULL, eventId INTEGER NOT NULL, FOREIGN KEY(eventId) REFERENCES events(id))')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def query_to_dicts(query, params=()):
    # TODO: HANDLE ERRORS
    conn = sqlite3.connect('entradas.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    dicts = [dict(row) for row in rows]
    conn.close()
    return dicts

def b3_client():
    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )
    return session.client('s3',
                               endpoint_url = endpoint_url,
                               config=Config(request_checksum_calculation="when_required",
                                             response_checksum_validation="when_required"))

def upload_file(file_object, file_key):
    # TODO: HANDLE ERRORS
    client = b3_client()
    client.upload_fileobj(file_object, bucket_name, file_key)

def download_file(file_key):
    # TODO: HANDLE ERRORS
    client = b3_client()
    return client.generate_presigned_url('get_object',
                                     Params={'Bucket': bucket_name, 'Key': file_key},
                                     ExpiresIn=60)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/event', methods=['GET'])
def get_events():

    events = query_to_dicts('SELECT * FROM events ORDER BY eventDate')
    return render_template('events.html', events=events)


@app.route('/event', methods=['POST'])
def add_event():

    with sqlite3.connect('entradas.db') as db:
        cursor = db.cursor()
        cursor.execute('INSERT INTO events values(null,?,?)',
                       (request.form['name'], request.form['date']))
        eventId = cursor.lastrowid

        files = request.files.getlist('tickets')
        if not files or all(file.filename == '' for file in files):
            return 'No selected files', 400

        for file_obj in files:
            print(type(file_obj))
            if file_obj.filename:
                file_key=f"{eventId}/{file_obj.filename}"
                upload_file(file_obj, file_key)
                cursor.execute('INSERT INTO tickets VALUES(null,?,?)', (file_key, eventId))
        db.commit()
        return get_events()


@app.route('/event/<event_id>', methods=['GET'])
def get_event(event_id):
    event = query_to_dicts('SELECT * FROM events WHERE id=?', (event_id,))[0]
    tickets = query_to_dicts('SELECT * FROM tickets WHERE eventId=?', (event_id,))
    return render_template('ticket.html', event=event, tickets=tickets)

@app.route('/ticket/<ticket_id>', methods=['GET'])
def get_ticket(ticket_id):
    ticket = query_to_dicts('SELECT * FROM tickets where id=?', (ticket_id,))[0]
    return redirect(download_file(ticket['ticketPath']), code='302')
