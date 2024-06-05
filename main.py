import json
import os
import time
from datadog import initialize, api
import requests
from datetime import datetime, timezone, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Config class to parse the configuration JSON file
class Config:
    def __init__(self, config_file):
        with open(config_file, 'r') as f:
            config_data = json.load(f)
            self.api_key = config_data['api_key']
            self.work_dir = config_data.get('work_dir', os.getcwd())
            self.datadog_api_key = config_data['datadog_api_key']
            self.datadog_app_key = config_data['datadog_app_key']
            self.thermostats = []
            for thermostat_config in config_data['thermostats']:
                thermostat_config['datadog_api_key'] = self.datadog_api_key
                thermostat_config['datadog_app_key'] = self.datadog_app_key
                self.thermostats.append(thermostat_config)

# Ecobee API client class
class EcobeeClient:
    def __init__(self, api_key, token_file):
        self.api_key = api_key
        self.token_file = token_file
        self.token = self.load_token()
        logging.debug(f"Loaded token from file: {self.token}")

        if self.token is None:
            logging.debug("Token file not found. Acquiring new token.")
            self.token = self.acquire_token()
            self.save_token(self.token)
            logging.debug(f"New token acquired: {self.token}")

    def load_token(self):
        if os.path.exists(self.token_file):
            with open(self.token_file, 'r') as f:
                return json.load(f)
        return None

    def save_token(self, token):
        with open(self.token_file, 'w') as f:
            json.dump(token, f)
        logging.debug(f"Token saved to file: {token}")

    def acquire_token(self):
        authorize_url = 'https://api.ecobee.com/authorize'
        params = {
            'response_type': 'ecobeePin',
            'client_id': self.api_key,
            'scope': 'smartRead'
        }
        response = requests.get(authorize_url, params=params)
        response.raise_for_status()
        auth_data = response.json()
        ecobee_pin = auth_data['ecobeePin']
        code = auth_data['code']

        print(f"Please authorize the app on the Ecobee portal using PIN: {ecobee_pin}")
        input("Press Enter once authorized...")

        token_url = 'https://api.ecobee.com/token'
        data = {
            'grant_type': 'ecobeePin',
            'code': code,
            'client_id': self.api_key
        }
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        token_data = response.json()
        token_data['expiry'] = str(time.time() + token_data['expires_in'])
        return token_data

    def refresh_token(self):
        url = 'https://api.ecobee.com/token'
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.token['refresh_token'],
            'client_id': self.api_key
        }
        response = requests.post(url, data=data)
        response.raise_for_status()
        self.token = response.json()
        self.token['expiry'] = str(time.time() + self.token['expires_in'])
        self.save_token(self.token)
        logging.debug(f"Token refreshed: {self.token}")

    def get_thermostat_data(self, thermostat_id):
        if datetime.now(timezone.utc) >= datetime.fromtimestamp(float(self.token['expiry']), tz=timezone.utc):
            logging.debug("Token has expired. Refreshing token.")
            self.refresh_token()

        url = f"https://api.ecobee.com/1/thermostat?json=%7B%22selection%22%3A%7B%22selectionType%22%3A%22thermostats%22%2C%22selectionMatch%22%3A%22{thermostat_id}%22%2C%22includeRuntime%22%3Atrue%2C%22includeExtendedRuntime%22%3Atrue%2C%22includeSettings%22%3Afalse%2C%22includeProgram%22%3Atrue%2C%22includeSensors%22%3Atrue%2C%22includeWeather%22%3Atrue%7D%7D"
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
            'Authorization': f'Bearer {self.token["access_token"]}'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        logging.debug(f"Thermostat data retrieved: {data}")
        return data['thermostatList'][0]

# Function to send data to Datadog
def send_to_datadog(thermostat_data, thermostat_config, last_written_runtime_interval, last_written_weather):
    initialize(api_key=thermostat_config['datadog_api_key'], app_key=thermostat_config['datadog_app_key'])
    logging.debug("Datadog initialized with the provided API key and app key.")

    thermostat_name = thermostat_data['name']
    tags = [f"thermostat_name:{thermostat_name}"]

    def send_metric(metric, points, tags):
        logging.debug(f"Sending metric {metric} with points {points} and tags {tags}")
        api.Metric.send(metric=metric, points=points, tags=tags)

    def send_temperature_metrics(report_time, temperature_f, heat_set_point_f, cool_set_point_f, demand_mgmt_offset_f, humidity, fan_run_time, suffix=""):
        temperature_c = (temperature_f - 32) * 5 / 9
        heat_set_point_c = (heat_set_point_f - 32) * 5 / 9
        cool_set_point_c = (cool_set_point_f - 32) * 5 / 9
        demand_mgmt_offset_c = (demand_mgmt_offset_f - 32) * 5 / 9
        points = [
            (report_time.timestamp(), temperature_f),
            (report_time.timestamp(), temperature_c),
            (report_time.timestamp(), heat_set_point_f),
            (report_time.timestamp(), heat_set_point_c),
            (report_time.timestamp(), cool_set_point_f),
            (report_time.timestamp(), cool_set_point_c),
            (report_time.timestamp(), demand_mgmt_offset_f),
            (report_time.timestamp(), demand_mgmt_offset_c),
            (report_time.timestamp(), humidity),
            (report_time.timestamp(), fan_run_time)
        ]
        logging.debug(f"Sending temperature metrics with suffix {suffix} at {report_time}")
        for point in points:
            logging.debug(f"Point: {point}")
        send_metric(f'ecobee.runtime.temperature_f{suffix}', [(report_time.timestamp(), temperature_f)], tags)
        send_metric(f'ecobee.runtime.temperature_c{suffix}', [(report_time.timestamp(), temperature_c)], tags)
        send_metric(f'ecobee.runtime.heat_set_point_f{suffix}', [(report_time.timestamp(), heat_set_point_f)], tags)
        send_metric(f'ecobee.runtime.heat_set_point_c{suffix}', [(report_time.timestamp(), heat_set_point_c)], tags)
        send_metric(f'ecobee.runtime.cool_set_point_f{suffix}', [(report_time.timestamp(), cool_set_point_f)], tags)
        send_metric(f'ecobee.runtime.cool_set_point_c{suffix}', [(report_time.timestamp(), cool_set_point_c)], tags)
        send_metric(f'ecobee.runtime.demand_mgmt_offset_f{suffix}', [(report_time.timestamp(), demand_mgmt_offset_f)], tags)
        send_metric(f'ecobee.runtime.demand_mgmt_offset_c{suffix}', [(report_time.timestamp(), demand_mgmt_offset_c)], tags)
        send_metric(f'ecobee.runtime.humidity{suffix}', [(report_time.timestamp(), humidity)], tags)
        send_metric(f'ecobee.runtime.fan_run_time{suffix}', [(report_time.timestamp(), fan_run_time)], tags)

    def send_optional_metrics(report_time, extended_runtime, i, thermostat_config):
        write_options = thermostat_config['write_options']
        if write_options.get('write_humidifier', False):
            desired_humidity = extended_runtime['desiredHumidity'][i]
            logging.debug(f"Sending ecobee.runtime.humidity_set_point with value {desired_humidity} at {report_time}")
            send_metric('ecobee.runtime.humidity_set_point', [(report_time.timestamp(), desired_humidity)], tags)
            humidifier_run_time = extended_runtime['humidifier'][i]
            logging.debug(f"Sending ecobee.runtime.humidifier_run_time with value {humidifier_run_time} at {report_time}")
            send_metric('ecobee.runtime.humidifier_run_time', [(report_time.timestamp(), humidifier_run_time)], tags)
        
        if write_options.get('write_dehumidifier', False):
            desired_dehumidity = extended_runtime['desiredDehumidity'][i]
            logging.debug(f"Sending ecobee.runtime.dehumidity_set_point with value {desired_dehumidity} at {report_time}")
            send_metric('ecobee.runtime.dehumidity_set_point', [(report_time.timestamp(), desired_dehumidity)], tags)
            dehumidifier_run_time = extended_runtime['dehumidifier'][i]
            logging.debug(f"Sending ecobee.runtime.dehumidifier_run_time with value {dehumidifier_run_time} at {report_time}")
            send_metric('ecobee.runtime.dehumidifier_run_time', [(report_time.timestamp(), dehumidifier_run_time)], tags)

        optional_metrics = {
            'aux_heat_1_run_time': extended_runtime['auxHeat1'][i],
            'aux_heat_2_run_time': extended_runtime['auxHeat2'][i],
            'heat_pump_1_run_time': extended_runtime['heatPump1'][i],
            'heat_pump_2_run_time': extended_runtime['heatPump2'][i],
            'cool_1_run_time': extended_runtime['cool1'][i],
            'cool_2_run_time': extended_runtime['cool2'][i]
        }

        for metric, value in optional_metrics.items():
            metric_name = metric.replace("_run_time", "")
            if write_options.get(f'write_{metric_name}', False):
                logging.debug(f"Sending {metric} with value {value} at {report_time}")
                send_metric(f'ecobee.runtime.{metric}', [(report_time.timestamp(), value)], tags)

    # Send air quality data
    runtime = thermostat_data['runtime']
    current_runtime_report_time = datetime.strptime(runtime['lastStatusModified'], '%Y-%m-%d %H:%M:%S')

    air_quality_metrics = {
        'ecobee.air_quality.accuracy': float(runtime.get('actualAQAccuracy', 0)),
        'ecobee.air_quality.score': float(runtime.get('actualAQScore', 0)),
        'ecobee.air_quality.co2': float(runtime.get('actualCO2', 0)),
        'ecobee.air_quality.voc': float(runtime.get('actualVOC', 0))
    }

    for metric, value in air_quality_metrics.items():
        logging.debug(f"Sending air quality metric {metric} with value {value} at {current_runtime_report_time}")
        send_metric(metric, [(current_runtime_report_time.timestamp(), value)], tags)

    # Send thermostat runtime data
    extended_runtime = thermostat_data['extendedRuntime']
    latest_runtime_interval = extended_runtime['runtimeInterval']
    logging.debug(f"Latest runtime interval available is {latest_runtime_interval}")
    base_report_time = datetime.strptime(extended_runtime['lastReadingTimestamp'], '%Y-%m-%d %H:%M:%S')
    for i in range(3):
        report_time = base_report_time + timedelta(minutes=(i - 1) * 5)
        if latest_runtime_interval != last_written_runtime_interval:
            temperature_f = extended_runtime['actualTemperature'][i] / 10.0
            heat_set_point_f = extended_runtime['desiredHeat'][i] / 10.0
            cool_set_point_f = extended_runtime['desiredCool'][i] / 10.0
            demand_mgmt_offset_f = extended_runtime['dmOffset'][i] / 10.0
            humidity = extended_runtime['actualHumidity'][i]
            fan_run_time = extended_runtime['fan'][i]

            send_temperature_metrics(report_time, temperature_f, heat_set_point_f, cool_set_point_f, demand_mgmt_offset_f, humidity, fan_run_time)
            send_optional_metrics(report_time, extended_runtime, i, thermostat_config)

    last_written_runtime_interval = latest_runtime_interval

    # Send sensor data
    sensor_time = datetime.strptime(thermostat_data['utcTime'], '%Y-%m-%d %H:%M:%S')
    for sensor in thermostat_data['remoteSensors']:
        try:
            sensor_name = sensor['name']
            for capability in sensor['capability']:
                if capability['type'] == 'temperature':
                    temp_f = int(capability['value']) / 10.0
                    temp_c = (temp_f - 32) * 5 / 9
                    logging.debug(f"Sending ecobee.sensor.temperature_c with value {temp_c} for sensor {sensor_name} at {sensor_time}")
                    send_metric('ecobee.sensor.temperature_c', [(sensor_time.timestamp(), temp_c)], [f"thermostat_name:{thermostat_name}", f"sensor_name:{sensor_name}"])
                    logging.debug(f"Sending ecobee.sensor.temperature_f with value {temp_f} for sensor {sensor_name} at {sensor_time}")
                    send_metric('ecobee.sensor.temperature_f', [(sensor_time.timestamp(), temp_f)], [f"thermostat_name:{thermostat_name}", f"sensor_name:{sensor_name}"])
                elif capability['type'] == 'occupancy':
                    occupied = capability['value'] == 'true'
                    logging.debug(f"Sending ecobee.sensor.occupied with value {occupied} for sensor {sensor_name} at {sensor_time}")
                    send_metric('ecobee.sensor.occupied', [(sensor_time.timestamp(), occupied)], [f"thermostat_name:{thermostat_name}", f"sensor_name:{sensor_name}"])
        except Exception as e:
            logging.error(f"An unexpected error occurred while processing sensor {sensor_name} on thermostat {thermostat_name}: {e}")

    # Send weather data
    weather_data = thermostat_data['weather']
    weather_time = datetime.strptime(weather_data['timestamp'], '%Y-%m-%d %H:%M:%S')
    outdoor_temp_f = weather_data['forecasts'][0]['temperature'] / 10.0
    outdoor_temp_c = (outdoor_temp_f - 32) * 5 / 9
    dewpoint_f = weather_data['forecasts'][0]['dewpoint'] / 10.0
    dewpoint_c = (dewpoint_f - 32) * 5 / 9

    pressure_mb = weather_data['forecasts'][0]['pressure']
    outdoor_humidity = weather_data['forecasts'][0]['relativeHumidity']
    wind_speed_mph = weather_data['forecasts'][0]['windSpeed']
    wind_bearing = weather_data['forecasts'][0]['windBearing']
    visibility_meters = weather_data['forecasts'][0]['visibility']
    visibility_miles = visibility_meters * 0.000621371
    weather_metrics = {
        'ecobee.weather.outdoor_temp_f': outdoor_temp_f,
        'ecobee.weather.outdoor_temp_c': outdoor_temp_c,
        'ecobee.weather.outdoor_humidity': outdoor_humidity,
        'ecobee.weather.barometric_pressure_mb': pressure_mb,
        'ecobee.weather.barometric_pressure_inHg': pressure_mb * 0.0295299830714,
        'ecobee.weather.dew_point_f': dewpoint_f,
        'ecobee.weather.dew_point_c': dewpoint_c,
        'ecobee.weather.wind_speed_mph': wind_speed_mph,
        'ecobee.weather.wind_bearing': wind_bearing,
        'ecobee.weather.visibility_mi': visibility_miles,
        'ecobee.weather.visibility_km': visibility_meters / 1000.0
    }

    always_write_weather_as_current = thermostat_config.get('always_write_weather_as_current', False)
    if weather_time != last_written_weather or always_write_weather_as_current:
        point_time = weather_time if not always_write_weather_as_current else datetime.now()
        for metric, value in weather_metrics.items():
            logging.debug(f"Sending weather metric {metric} with value {value} at {point_time}")
            send_metric(metric, [(point_time.timestamp(), value)], [f"thermostat_name:{thermostat_name}", "data_source:ecobee"])

        last_written_weather = weather_time

    return last_written_runtime_interval, last_written_weather

def main():
    config_file = 'config.json'
    config = Config(config_file)
    logging.debug(f"Loaded configuration from file: {config_file}")

    token_file = os.path.join(config.work_dir, 'ecobee_token.json')
    client = EcobeeClient(config.api_key, token_file)

    last_written_runtime_intervals = {}
    last_written_weathers = {}

    while True:
        for thermostat_config in config.thermostats:
            thermostat_id = thermostat_config['id']
            try:
                thermostat_data = client.get_thermostat_data(thermostat_id)
                logging.debug(f"Retrieved thermostat data for {thermostat_id}: {thermostat_data}")

                last_written_runtime_interval = last_written_runtime_intervals.get(thermostat_id, 0)
                last_written_weather = last_written_weathers.get(thermostat_id, None)

                last_written_runtime_interval, last_written_weather = send_to_datadog(thermostat_data, thermostat_config, last_written_runtime_interval, last_written_weather)
                logging.debug(f"Data sent to Datadog for thermostat {thermostat_id}.")

                last_written_runtime_intervals[thermostat_id] = last_written_runtime_interval
                last_written_weathers[thermostat_id] = last_written_weather

            except requests.exceptions.HTTPError as e:
                logging.error(f"HTTP error occurred while fetching data for thermostat {thermostat_id}: {e}")
            except Exception as e:
                logging.error(f"An unexpected error occurred while processing thermostat {thermostat_id}: {e}")

        logging.debug("Waiting for 5 minutes before the next update.")
        time.sleep(300)  # Wait for 5 minutes before next update

if __name__ == '__main__':
    main()