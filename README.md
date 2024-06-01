# Ecobee Data to Datadog

## Overview

This project provides a solution for retrieving data from Ecobee thermostats and sending it to Datadog for monitoring and visualization. It is designed to run continuously, collecting thermostat data at regular intervals and transmitting it to Datadog as metrics.

## Features

- Retrieves detailed data from Ecobee thermostats, including temperature, humidity, runtime, and sensor data.
- Sends collected data to Datadog for real-time monitoring and visualization.
- Supports multiple thermostats with customizable configuration options.
- Automatically handles token acquisition and refresh for Ecobee API authentication.
- Configurable logging for monitoring the data collection and transmission process.

## Prerequisites

- Python 3.7+
- Datadog API and Application keys
- Ecobee Developer API key
- Ecobee thermostats with read access

## Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/yourusername/ecobee-datadog.git
    cd ecobee-datadog
    ```

2. Install the required Python packages:

    ```bash
    pip install -r requirements.txt
    ```

3. Configure your environment:

    Create a `config.json` file in the project root with your API keys and thermostat configurations. An example configuration is provided below:

    ```json
    {
        "api_key": "your_ecobee_api_key",
        "datadog_api_key": "your_datadog_api_key",
        "datadog_app_key": "your_datadog_app_key",
        "thermostats": [
            {
                "id": "your_thermostat_id_1",
                "write_options": {
                    "write_heat_pump_1": true,
                    "write_heat_pump_2": false,
                    "write_aux_heat_1": true,
                    "write_aux_heat_2": false,
                    "write_cool_1": true,
                    "write_cool_2": false,
                    "write_humidifier": false,
                    "write_dehumidifier": true
                },
                "always_write_weather_as_current": false
            },
            {
                "id": "your_thermostat_id_2",
                "write_options": {
                    "write_heat_pump_1": false,
                    "write_heat_pump_2": false,
                    "write_aux_heat_1": true,
                    "write_aux_heat_2": false,
                    "write_cool_1": true,
                    "write_cool_2": false,
                    "write_humidifier": true,
                    "write_dehumidifier": false
                },
                "always_write_weather_as_current": false
            }
        ]
    }
    ```

## Usage

To start the data collection and transmission process, run the `main.py` script:

```bash
python main.py
```

The script will continuously run, collecting data every 5 minutes and sending it to Datadog. Ensure that you have authorized the app on the Ecobee portal when prompted.

## Configuration

The `config.json` file allows you to customize various aspects of the data collection and transmission process. Below is a description of the configurable parameters:

- `api_key`: Your Ecobee Developer API key.
- `datadog_api_key`: Your Datadog API key.
- `datadog_app_key`: Your Datadog Application key.
- `thermostats`: A list of thermostat configurations, each containing:
  - `id`: The unique ID of the thermostat.
  - `write_options`: A dictionary specifying which metrics to send to Datadog.
  - `always_write_weather_as_current`: If true, always writes weather data as the current time.

## Logging

The script includes configurable logging to monitor the data collection and transmission process. Logs are written to the console and include timestamps and log levels for easy debugging.

## Contributing

We welcome contributions to this project! To contribute:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature-branch`).
3. Make your changes and commit them (`git commit -am 'Add new feature'`).
4. Push to the branch (`git push origin feature-branch`).
5. Create a new Pull Request.