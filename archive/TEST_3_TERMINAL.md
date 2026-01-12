# Terminal Commands

## Terminal 1: Start Broker

cd D:\CODE\Zigbee-Flow-Monitoring-System
.\start_broker.ps1

## Terminal 2: Start Gateway

cd D:\CODE\Zigbee-Flow-Monitoring-System\wfms
python -m gateway.service

## Terminal 3: Subscribe MQTT để xem data

mosquitto_sub -h 26.172.222.181 -t "wfms/lab1/#" -v

## Terminal 4: Test valve command

mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/valve' -m '{\"cid\":\"test\",\"value\":\"ON\",\"by\":\"admin\"}'