from flask import Flask, request, jsonify, render_template
import requests
from dotenv import load_dotenv
import os
import logging
from math import radians, cos, sin, sqrt, atan2

class WeatherRouteApp:
    def __init__(self):
        load_dotenv()  # Load environment variables from .env file
        self.app = Flask(__name__)
        self.GOOGLE_MAPS_API_KEY = os.getenv('MAPS_API_KEY')
        self.setup_logging()
        self.setup_routes()

    def setup_logging(self):
        logging.basicConfig(level=logging.DEBUG)
        self.app.logger.setLevel(logging.DEBUG)

    def setup_routes(self):
        @self.app.route('/')
        def index():
            api_key = os.getenv('MAPS_API_KEY')
            return render_template('index.html', api_key=api_key)
        

        @self.app.route('/getRoute', methods=['POST'])
        def get_route():
            try:
                source = request.form['source']
                destination = request.form['destination']

                directions_url = 'https://maps.googleapis.com/maps/api/directions/json'
                directions_params = {
                    'origin': source,
                    'destination': destination,
                    'key': self.GOOGLE_MAPS_API_KEY
                }
                directions_response = requests.get(directions_url, params=directions_params)
                directions_response.raise_for_status()  # Raise HTTPError for bad responses
                directions_data = directions_response.json()

                route = directions_data['routes'][0]['overview_polyline']['points']
                steps = directions_data['routes'][0]['legs'][0]['steps']
                cities = self.extract_major_cities(steps)

                cities_weather = []
                for city in cities:
                    weather = self.get_city_weather(city)
                    if weather:
                        cities_weather.append({
                            'city': city,
                            'weather': weather
                        })

                return jsonify({'route': route, 'cities_weather': cities_weather})
            except Exception as e:
                self.app.logger.error(f"Error in get_route: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/getCityLatLon', methods=['GET'])
        def get_city_lat_lon():
            city = request.args.get('city')
            lat, lon = self.get_lat_lon(city)
            return jsonify({'lat': lat, 'lon': lon})

    # def extract_major_cities(self, steps):
    #     cities = []
    #     last_location = None

    #     for step in steps:
    #         end_location = step['end_location']
    #         if last_location:
    #             distance = self.haversine_distance(last_location['lat'], last_location['lng'], end_location['lat'], end_location['lng'])
    #             if distance < 20:  # Skip locations less than 20 miles apart
    #                 continue
    #         city = self.reverse_geocode(end_location['lat'], end_location['lng'])
    #         if city and (not cities or city != cities[-1]):  # Avoid duplicate cities
    #             cities.append(city)
    #             last_location = end_location
    #     return cities

    def extract_major_cities(self, steps):
        cities = []
        counties = set()  # Keep track of counties already added
        last_location = None

        for step in steps:
            end_location = step['end_location']
            if last_location:
                distance = self.haversine_distance(last_location['lat'], last_location['lng'], end_location['lat'], end_location['lng'])
                if distance < 30:  # Skip locations less than 20 miles apart
                    continue
            city = self.reverse_geocode(end_location['lat'], end_location['lng'])
            county = self.reverse_geocode(end_location['lat'], end_location['lng'], reverse_type='administrative_area_level_2')
            if city:
                if county and county not in counties:  # Add city if county exists and not added before
                    cities.append(city)
                    counties.add(county)
                elif not county:  # If county not found, add city
                    cities.append(city)
                last_location = end_location
        return cities


    def haversine_distance(self, lat1, lon1, lat2, lon2):
        R = 3958.8  # Earth radius in miles
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    def reverse_geocode(self, lat, lng, reverse_type='locality'):
        try:
            geocode_url = 'https://maps.googleapis.com/maps/api/geocode/json'
            geocode_params = {
                'latlng': f'{lat},{lng}',
                'result_type': reverse_type,
                'key': self.GOOGLE_MAPS_API_KEY
            }
            response = requests.get(geocode_url, params=geocode_params)
            response.raise_for_status()  # Raise HTTPError for bad responses
            geocode_data = response.json()
            if geocode_data['results']:
                for component in geocode_data['results'][0]['address_components']:
                    if reverse_type in component['types']:
                        return component['long_name']
        except Exception as e:
            self.app.logger.error(f"Error in reverse_geocode: {e}")
        return None


    def get_lat_lon(self, city):
        geocode_url = 'https://maps.googleapis.com/maps/api/geocode/json'
        geocode_params = {
            'address': city,
            'key': self.GOOGLE_MAPS_API_KEY
        }
        response = requests.get(geocode_url, params=geocode_params)
        response.raise_for_status()
        geocode_data = response.json()
        if geocode_data['results']:
            location = geocode_data['results'][0]['geometry']['location']
            return location['lat'], location['lng']
        return None, None

    def get_grid_points(self, lat, lon):
        points_url = f"https://api.weather.gov/points/{lat},{lon}"
        response = requests.get(points_url)
        response.raise_for_status()
        points_data = response.json()
        properties = points_data['properties']
        return properties['gridId'], properties['gridX'], properties['gridY']

    def get_forecast(self, grid_id, grid_x, grid_y):
        forecast_url = f"https://api.weather.gov/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast/hourly"
        response = requests.get(forecast_url)
        response.raise_for_status()
        forecast_data = response.json()
        periods = forecast_data['properties']['periods'][:12]  # Get the next 12 hours
        return [{'time': period['startTime'], 'temperature': period['temperature'], 'temperatureUnit': period['temperatureUnit'], 'shortForecast': period['shortForecast']} for period in periods]

    def get_city_weather(self, city):
        try:
            lat, lon = self.get_lat_lon(city)
            if lat is None or lon is None:
                raise ValueError(f"Unable to find coordinates for city: {city}")

            grid_id, grid_x, grid_y = self.get_grid_points(lat, lon)
            forecast = self.get_forecast(grid_id, grid_x, grid_y)
            return forecast
        except Exception as e:
            self.app.logger.error(f"Error in get_city_weather: {e}")
            return None

    def run(self, port=5000):
        self.app.run(port=port, debug=True)
      

if __name__ == '__main__':
    app = WeatherRouteApp()
    app.run()
