from flask import Flask, request, jsonify, render_template
import requests
from geopy.distance import geodesic
from dotenv import load_dotenv
import os
import logging

class WeatherRouteApp:
    def __init__(self):
        load_dotenv()  # Load environment variables from .env file
        self.app = Flask(__name__)
        self.GOOGLE_MAPS_API_KEY = os.getenv('MAPS_API_KEY')
        self.OPENWEATHERMAP_API_KEY = os.getenv('WEATHER_API_KEY')
        self.setup_logging()
        self.setup_routes()

    def setup_logging(self):
        logging.basicConfig(level=logging.DEBUG)
        self.app.logger.setLevel(logging.DEBUG)

    def setup_routes(self):
        @self.app.route('/')
        def index():
            api_key = self.GOOGLE_MAPS_API_KEY
            return render_template('index.html', api_key=api_key)

        @self.app.route('/getRoute', methods=['POST'])
        def get_route():
            try:
                data = request.get_json()
                source = data['source']
                destination = data['destination']

                directions_url = 'https://maps.googleapis.com/maps/api/directions/json'
                directions_params = {
                    'origin': source,
                    'destination': destination,
                    'key': self.GOOGLE_MAPS_API_KEY
                }
                directions_response = requests.get(directions_url, params=directions_params)
                directions_response.raise_for_status()  # Raise HTTPError for bad responses
                directions_data = directions_response.json()

                steps = directions_data['routes'][0]['legs'][0]['steps']
                cities = self.extract_cities_from_route(steps)

                cities_weather = []
                for city in cities:
                    weather = self.get_city_weather(city)
                    if weather:
                        cities_weather.append({
                            'city': city,
                            'weather': weather
                        })

                return jsonify({
                    'route': directions_data['routes'][0]['overview_polyline']['points'],
                    'cities_weather': cities_weather
                })
            except Exception as e:
                self.app.logger.error(f"Error in get_route: {e}")
                return jsonify({'error': str(e)}), 500

    def extract_cities_from_route(self, steps):
        waypoints = [(step['end_location']['lat'], step['end_location']['lng']) for step in steps]

        cities = []
        previous_point = waypoints[0]
        distance_accumulated = 0

        for point in waypoints[1:]:
            distance = geodesic(previous_point, point).miles
            distance_accumulated += distance

            if distance_accumulated >= 30:
                city_info = self.get_city_info(point)
                if city_info:
                    cities.append(city_info)
                previous_point = point
                distance_accumulated = 0

        return cities

    def get_city_info(self, location):
        lat, lng = location
        geocode_url = 'https://maps.googleapis.com/maps/api/geocode/json'
        geocode_params = {
            'latlng': f'{lat},{lng}',
            'key': self.GOOGLE_MAPS_API_KEY
        }
        response = requests.get(geocode_url, params=geocode_params)
        response.raise_for_status()
        geocode_data = response.json()
        if geocode_data['results']:
            for result in geocode_data['results']:
                for component in result['address_components']:
                    if 'locality' in component['types']:
                        return component['long_name']
        return None

    def get_city_weather(self, city):
        try:
            url = f'https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={self.OPENWEATHERMAP_API_KEY}&units=metric'
            response = requests.get(url)
            response.raise_for_status()
            weather_data = response.json()

            # Extract the weather information for the next 5 hours or the specified travel time
            weather_info = []
            for forecast in weather_data['list'][:5]:  # Limit to the next 5 forecasts (next 15 hours)
                weather_info.append({
                    'time': forecast['dt_txt'],
                    'weather': forecast['weather'][0]['description'],
                    'temperature': forecast['main']['temp']
                })

            return weather_info
        except Exception as e:
            self.app.logger.error(f"Error in get_city_weather: {e}")
            return None

    def run(self, port=5000):
        self.app.run(port=port, debug=True)

if __name__ == '__main__':
    app = WeatherRouteApp()
    app.run()
