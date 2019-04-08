import json
from flask import Flask, request, redirect
import requests
import base64
import urllib.parse
from six import text_type
import spotipy
import numpy as np

app = Flask(__name__)

# Client Keys
CLIENT_ID = '1f6397c5617841b9a104f750bd309a37'
CLIENT_SECRET = '442fd02c347a41e19477ce4908712f2f'

# Spotify URLS
SPOTIFY_AUTH_URL = 'https://accounts.spotify.com/authorize'
SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_API_BASE_URL = 'https://api.spotify.com'
API_VERSION = 'v1'
SPOTIFY_API_URL = "{}/{}".format(SPOTIFY_API_BASE_URL, API_VERSION)


# Server-side Parameters
CLIENT_SIDE_URL = 'http://localhost'
PORT = 5000
REDIRECT_URI = "{}:{}/callback".format(CLIENT_SIDE_URL, PORT)
SCOPE = 'playlist-modify-private user-top-read'
STATE = ''
SHOW_DIALOG_bool = True
SHOW_DIALOG_str = str(SHOW_DIALOG_bool).lower()
REGRESSION = 0.95
TRACK_FEATURE_SCOPE = 20

auth_query_parameters = {
    'response_type': 'code',
    'redirect_uri': REDIRECT_URI,
    'scope': SCOPE,
    #'state': STATE,
    'show_dialog': SHOW_DIALOG_str,
    'client_id': CLIENT_ID
}

def get_user_auth_header(access_token):
    return {"Authorization":"Bearer {}".format(access_token)}

@app.route('/login')
def login():
    # Get user authorization
    url_args = '&'.join(['{}={}'.format(key,urllib.parse.quote(val)) for key,val in auth_query_parameters.items()])
    auth_url = '{}/?{}'.format(SPOTIFY_AUTH_URL, url_args)
    return redirect(auth_url)


@app.route('/callback')
def callback():
    # Request refresh and access token
    auth_token = request.args['code']
    code_payload = {
        'grant_type': 'authorization_code',
        'code': str(auth_token),
        'redirect_uri': REDIRECT_URI
    }
    base64encoded = base64.b64encode(text_type(CLIENT_ID + ':' + CLIENT_SECRET).encode('ascii'))
    headers = {'Authorization': 'Basic {}'.format(base64encoded.decode('ascii'))}
    post_request = requests.post(SPOTIFY_TOKEN_URL, data=code_payload, headers=headers)

    # Load tokens
    response_data = json.loads(post_request.text)
    access_token = response_data['access_token']
    refresh_token = response_data['refresh_token']

    # Create response url
    res_query_parameters = {
        'access_token': access_token,
        'refresh_token': refresh_token
    }
    url_args = '&'.join(['{}={}'.format(key,urllib.parse.quote(val)) for key,val in res_query_parameters.items()])
    res_url = '{}/#{}'.format(CLIENT_SIDE_URL + ':3000', url_args)

    return redirect(res_url)


@app.route('/create_blend/<limit>/<time_range>', methods=['POST', 'GET'])
def create_blend(limit, time_range):
    blend_seed = {'tracks': {}, 'artists': {}, 'genres': {}}
    if request.method == 'POST':
        for user in request.form:
            token = request.form[user]
            sp = spotipy.Spotify(auth=token)
            top_tracks = sp.current_user_top_tracks(limit=limit, offset=0, time_range=time_range)
            weight = 1.0
            for track in range(0, int(limit)):
                if top_tracks['items'][track]['id'] in blend_seed['tracks']:
                    blend_seed['tracks'][top_tracks['items'][track]['id']] += weight
                else:
                    blend_seed['tracks'][top_tracks['items'][track]['id']] = weight
                for artist in top_tracks['items'][track]['artists']:
                    if artist['id'] in blend_seed['artists']:
                        blend_seed['artists'][artist['id']] += weight
                    else:
                        blend_seed['artists'][artist['id']] = weight
                weight *= REGRESSION
        seed_artists = get_seed_artists(blend_seed['artists'])
        print(seed_artists)
        target_args = get_target_args(blend_seed['tracks'], 20, sp)
        recommendations = sp.recommendations(seed_artists=seed_artists, limit=100,
        **target_args)
        print(recommendations)
    return 'success'

# Helper function -  orders IDs by weight
def sort_by_weight(blend_seed_attributes):
    return {k: v for k, v in sorted(blend_seed_attributes.items(), key=lambda x: -x[1])}

# Gets artists with the 5 highest weights
def get_seed_artists(blend_seed_artists):
    return list(sort_by_weight(blend_seed_artists).keys())[:5]

# Creates target audio characteristics for the top N songs
def get_target_args(blend_seed_tracks, n, sp):
    top_tracks = [i for i in sort_by_weight(blend_seed_tracks)][:n]
    top_tracks_features = sp.audio_features(top_tracks)
    target_args = {
        'target_danceability': str(np.mean([i['danceability'] for i in top_tracks_features])),
        'target_energy': str(np.mean([i['energy'] for i in top_tracks_features])),
        'target_loudness': str(np.mean([i['loudness'] for i in top_tracks_features])),
        'target_instrumentalness': str(np.mean([i['instrumentalness'] for i in top_tracks_features])),
        'target_valence': str(np.mean([i['valence'] for i in top_tracks_features]))
    }
    return target_args
