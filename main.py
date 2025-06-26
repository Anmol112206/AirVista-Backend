import os
import firebase_admin
from firebase_admin import credentials, firestore
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask_cors import CORS
from mailjet_rest import Client

load_dotenv()

app = Flask(__name__)
CORS(app)


cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
AQI_TOKEN = os.getenv("TOKEN")
api_key =  os.getenv("MAILJET_PUBLIC_KEY")
api_secret =  os.getenv("MAILJET_PRIVATE_KEY")
alert_threshold = int(os.getenv("ALERT_THRESHOLD"))


mailjet = Client(auth=(api_key, api_secret), version='v3.1')


def get_aqi(city):
    url = f"https://api.waqi.info/feed/{city}/?token={AQI_TOKEN}"
    res = requests.get(url)
    data = res.json()
    if data.get("status") == "ok":
        return data["data"]["aqi"]
    return None


@app.route("/aqi")
def aqi_endpoint():
    city = request.args.get("city")
    if not city:
        return jsonify({"error": "City parameter missing"}), 400
    url = f"https://api.waqi.info/feed/{city}/?token={AQI_TOKEN}"
    res = requests.get(url)
    data = res.json()   
    return jsonify(data)

@app.route("/weather")
def weather_endpoint():
    city = request.args.get("city")
    if not city:
        return jsonify({"error": "City parameter missing"}), 400

    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
    
    try:
        res = requests.get(url)
        data = res.json()

        if data.get("cod") != 200:
            return jsonify({"status": "error", "message": data.get("message", "Unknown error")}), 404

        return jsonify(data)

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def send_aqi_email(to_email, city, aqi_value,name):
    subject = f"⚠️ AQI Alert in {city}"
    message = f"AQI level in {city} is {aqi_value}."
    
    data = {
        'Messages': [
            {
                "From": {
                    "Email": "airvistaaqialert@gmail.com",  
                    "Name": "AirVista"
                },
                "To": [
                    {
                        "Email": to_email,
                        "Name": name
                    }
                ],
                "Subject": subject,
                "TextPart": message,
                "HTMLPart": f"<h3>{subject}</h3><p>{message}</p>",
            }
        ]
    }

    result = mailjet.send.create(data=data)



def run_notifier():
    users_ref = db.collection("users")
    users = users_ref.stream()
    for user in users:
        uid = user.id
        user_data = user.to_dict()
        cities = user_data.get("cities", [])
        name = user_data.get("username", "User")
        email = user_data.get("email")
        checkbox = user_data.get("getEmails")
        
        for city in cities:
            aqi = get_aqi(city)
            if aqi is not None and aqi >= alert_threshold :
                notification = {
                    "title": f"⚠ AQI Alert ",
                    "body": f"AQI level in {city} is {aqi}.",
                    "timestamp": firestore.SERVER_TIMESTAMP,
                    "read": False
                }
                if email and checkbox:
                    send_aqi_email(email, city, aqi,name)

                db.collection("users").document(uid) \
                    .collection("notifications").add(notification)



@app.route('/run')
def run():
    run_notifier()
    return "✅ AQI Notification Sent!"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
