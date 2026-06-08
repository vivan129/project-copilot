"""
RAG service — seeds and queries ChromaDB for component and project knowledge.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from app.config import settings

logger = logging.getLogger(__name__)

# ── Collections ──────────────────────────────────────────────────────────────
COMPONENTS_COLLECTION = "components"
PROJECTS_COLLECTION = "project_templates"

# ── Engineering knowledge base ───────────────────────────────────────────────
COMPONENT_KNOWLEDGE: list[dict[str, Any]] = [
    # ── Microcontrollers ──
    {
        "id": "arduino-uno",
        "text": "Arduino Uno R3: ATmega328P, 14 digital I/O pins (6 PWM), 6 analog inputs, 16 MHz, 5V. "
                "Beginner-friendly. Best for simple sensors, LEDs, motors. Price: $25-30.",
        "metadata": {"category": "microcontroller", "difficulty": 1, "price_usd": 27},
    },
    {
        "id": "arduino-nano",
        "text": "Arduino Nano: ATmega328P, compact form factor, USB-B mini, breadboard-friendly. "
                "Same capabilities as Uno but tiny. Great for wearables, compact projects. Price: $3-8.",
        "metadata": {"category": "microcontroller", "difficulty": 1, "price_usd": 5},
    },
    {
        "id": "esp32",
        "text": "ESP32: Dual-core Xtensa 240 MHz, WiFi + Bluetooth, 34 GPIO, 4MB flash, ADC/DAC. "
                "Perfect for IoT, smart home, MQTT, web server. Price: $5-10.",
        "metadata": {"category": "microcontroller", "difficulty": 2, "price_usd": 8},
    },
    {
        "id": "esp8266",
        "text": "ESP8266: WiFi-enabled, 80 MHz, 11 GPIO. Budget IoT choice. "
                "Good for simple cloud connectivity. Price: $2-5.",
        "metadata": {"category": "microcontroller", "difficulty": 2, "price_usd": 3},
    },
    {
        "id": "raspberry-pi-4",
        "text": "Raspberry Pi 4: 1.8 GHz quad-core ARM, 2-8 GB RAM, USB 3.0, HDMI, Ethernet, WiFi. "
                "Runs Linux. Best for computer vision, AI inference, media centers, servers. Price: $35-75.",
        "metadata": {"category": "sbc", "difficulty": 3, "price_usd": 55},
    },
    {
        "id": "raspberry-pi-pico",
        "text": "Raspberry Pi Pico: RP2040 dual-core, 264KB RAM, 2MB flash, 26 GPIO, ADC, PWM. "
                "MicroPython or C/C++. Great for real-time control, cheap IoT. Price: $4.",
        "metadata": {"category": "microcontroller", "difficulty": 2, "price_usd": 4},
    },
    # ── Sensors ──
    {
        "id": "hc-sr04",
        "text": "HC-SR04 Ultrasonic Sensor: 2cm-400cm range, ±3mm accuracy, 5V, Trig+Echo pins. "
                "Perfect for obstacle detection, distance measurement. Price: $1-3.",
        "metadata": {"category": "sensor", "difficulty": 1, "price_usd": 2},
    },
    {
        "id": "dht22",
        "text": "DHT22 Temperature & Humidity Sensor: -40 to 80°C, 0-100% RH, single-wire protocol. "
                "Better than DHT11. Weather station, HVAC automation. Price: $2-5.",
        "metadata": {"category": "sensor", "difficulty": 1, "price_usd": 3},
    },
    {
        "id": "pir-motion",
        "text": "PIR Motion Sensor (HC-SR501): Passive infrared, 3-7m range, adjustable sensitivity/delay. "
                "Perfect for security systems, smart lights, intruder alerts. Price: $1-3.",
        "metadata": {"category": "sensor", "difficulty": 1, "price_usd": 2},
    },
    {
        "id": "soil-moisture",
        "text": "Capacitive Soil Moisture Sensor v1.2: Capacitive (no corrosion), analog output, 3.3V-5V. "
                "Plant watering automation, agriculture projects. Price: $2-5.",
        "metadata": {"category": "sensor", "difficulty": 1, "price_usd": 3},
    },
    {
        "id": "mpu6050",
        "text": "MPU-6050 6-axis IMU: 3-axis gyro + 3-axis accelerometer, I2C, DMP. "
                "Balance bots, gesture control, flight controllers, angle measurement. Price: $1-4.",
        "metadata": {"category": "sensor", "difficulty": 2, "price_usd": 2},
    },
    {
        "id": "camera-module",
        "text": "Raspberry Pi Camera Module v2: 8MP Sony IMX219, 1080p30, 720p60, wide aperture. "
                "Computer vision, security cam, time-lapse, ML inference. Price: $25-30.",
        "metadata": {"category": "sensor", "difficulty": 3, "price_usd": 28},
    },
    # ── Actuators ──
    {
        "id": "sg90-servo",
        "text": "SG90 Micro Servo: 180°, 2.5kg·cm torque, PWM control, 4.8V-6V. "
                "Robot arms, pan-tilt cameras, door locks. Price: $1-3.",
        "metadata": {"category": "actuator", "difficulty": 1, "price_usd": 2},
    },
    {
        "id": "l298n-motor-driver",
        "text": "L298N Motor Driver: Dual H-bridge, 2A per channel, 5-35V motor supply, 5V logic. "
                "2WD/4WD robot cars, DC motor control. Price: $2-5.",
        "metadata": {"category": "actuator", "difficulty": 2, "price_usd": 3},
    },
    {
        "id": "stepper-nema17",
        "text": "NEMA 17 Stepper Motor + A4988 driver: 200 steps/rev, 1/16 microstepping. "
                "CNC, 3D printers, linear actuators, precise positioning. Price: $10-20.",
        "metadata": {"category": "actuator", "difficulty": 3, "price_usd": 15},
    },
    {
        "id": "relay-module",
        "text": "5V Single Channel Relay Module: Controls 250VAC/10A, optocoupler isolation, active low. "
                "Smart switches, appliance control, automated watering pumps. Price: $1-3.",
        "metadata": {"category": "actuator", "difficulty": 1, "price_usd": 2},
    },
    # ── Displays ──
    {
        "id": "oled-096",
        "text": "0.96\" OLED I2C Display: 128×64 pixels, SSD1306 driver, 3.3V-5V, I2C address 0x3C. "
                "Status displays, sensor dashboards, portable projects. Price: $2-5.",
        "metadata": {"category": "display", "difficulty": 1, "price_usd": 3},
    },
    {
        "id": "lcd-1602",
        "text": "16x2 LCD with I2C backpack: 16 characters × 2 lines, backlight, I2C (saves pins). "
                "Text menus, readings display, clock projects. Price: $2-5.",
        "metadata": {"category": "display", "difficulty": 1, "price_usd": 3},
    },
    # ── Communication ──
    {
        "id": "nrf24l01",
        "text": "nRF24L01+ 2.4GHz Wireless Module: 250kbps-2Mbps, 100m range, SPI, 1.9V-3.6V. "
                "RC cars, wireless sensor networks, multi-robot comms. Price: $1-3.",
        "metadata": {"category": "communication", "difficulty": 2, "price_usd": 2},
    },
    {
        "id": "sim800l",
        "text": "SIM800L GSM/GPRS Module: SMS, calls, GPRS data, Quad-band, AT commands. "
                "Remote IoT alerts, SMS security systems, GPS trackers. Price: $4-8.",
        "metadata": {"category": "communication", "difficulty": 3, "price_usd": 6},
    },
]

PROJECT_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "line-follower-robot",
        "text": "Line Follower Robot: Arduino Uno + L298N + IR sensors. "
                "2 DC motors follow black line on white surface. Uses PID control. "
                "Build time: 6-8 hours. Difficulty: beginner. Good science fair project.",
        "metadata": {"category": "robotics", "difficulty": 2, "hours": 7},
    },
    {
        "id": "smart-plant-watering",
        "text": "Smart Plant Watering System: ESP8266 + soil moisture sensor + relay + pump. "
                "Auto-waters when dry, sends mobile alerts via MQTT/Blynk. "
                "Build time: 4-6 hours. Difficulty: beginner.",
        "metadata": {"category": "iot", "difficulty": 1, "hours": 5},
    },
    {
        "id": "obstacle-avoidance-robot",
        "text": "Obstacle Avoidance Robot: Arduino + HC-SR04 ultrasonic + L298N + servo. "
                "Turns automatically when obstacle detected, servo sweeps for direction. "
                "Build time: 4-6 hours. Classic robotics project.",
        "metadata": {"category": "robotics", "difficulty": 2, "hours": 5},
    },
    {
        "id": "weather-station",
        "text": "IoT Weather Station: ESP32 + DHT22 + BMP180 + OLED. "
                "Logs temperature, humidity, pressure to cloud dashboard. "
                "Build time: 3-5 hours. Difficulty: beginner. Great for science fair.",
        "metadata": {"category": "iot", "difficulty": 1, "hours": 4},
    },
    {
        "id": "home-security",
        "text": "Home Security System: Raspberry Pi + PIR sensors + camera + Telegram bot. "
                "Detects motion, sends photo alerts to phone, 24/7 recording. "
                "Build time: 8-12 hours. Difficulty: intermediate.",
        "metadata": {"category": "iot", "difficulty": 3, "hours": 10},
    },
    {
        "id": "self-balancing-robot",
        "text": "Self-Balancing Robot: Arduino + MPU6050 + L298N + PID controller. "
                "Two-wheeled inverted pendulum. Tune PID gains for stability. "
                "Build time: 12-16 hours. Difficulty: advanced. Impressive demo project.",
        "metadata": {"category": "robotics", "difficulty": 4, "hours": 14},
    },
    {
        "id": "voice-assistant-pi",
        "text": "Raspberry Pi Voice Assistant: Pi 4 + microphone + speaker + Google Speech API. "
                "Custom wake word, local commands, internet search integration. "
                "Build time: 8-10 hours. Difficulty: intermediate.",
        "metadata": {"category": "raspberry_pi", "difficulty": 3, "hours": 9},
    },
]


class RAGService:
    _client: chromadb.ClientAPI | None = None

    def _get_client(self) -> chromadb.ClientAPI:
        if self._client is None:
            self._client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        return self._client

    def _embedding_fn(self):
        """Use sentence-transformers (no API key needed) or a simple hash fallback."""
        try:
            return embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
        except Exception:
            return embedding_functions.DefaultEmbeddingFunction()

    def seed_knowledge_base(self) -> None:
        """Seed ChromaDB with component and project knowledge. Idempotent."""
        client = self._get_client()
        ef = self._embedding_fn()

        # ── Components ──────────────────────────────────────────────────────
        comp_col = client.get_or_create_collection(
            COMPONENTS_COLLECTION, embedding_function=ef
        )
        existing_ids = set(comp_col.get()["ids"])
        new_items = [c for c in COMPONENT_KNOWLEDGE if c["id"] not in existing_ids]
        if new_items:
            comp_col.add(
                ids=[c["id"] for c in new_items],
                documents=[c["text"] for c in new_items],
                metadatas=[c["metadata"] for c in new_items],
            )
            logger.info("Seeded %d component docs into ChromaDB", len(new_items))

        # ── Project templates ────────────────────────────────────────────────
        proj_col = client.get_or_create_collection(
            PROJECTS_COLLECTION, embedding_function=ef
        )
        existing_ids = set(proj_col.get()["ids"])
        new_items = [p for p in PROJECT_TEMPLATES if p["id"] not in existing_ids]
        if new_items:
            proj_col.add(
                ids=[p["id"] for p in new_items],
                documents=[p["text"] for p in new_items],
                metadatas=[p["metadata"] for p in new_items],
            )
            logger.info("Seeded %d project templates into ChromaDB", len(new_items))

    def retrieve_component_docs(self, query: str, n_results: int = 5) -> list[str]:
        """Return relevant component docs for a query."""
        try:
            client = self._get_client()
            ef = self._embedding_fn()
            col = client.get_or_create_collection(COMPONENTS_COLLECTION, embedding_function=ef)
            if col.count() == 0:
                self.seed_knowledge_base()
            result = col.query(query_texts=[query], n_results=min(n_results, col.count()))
            return result["documents"][0] if result["documents"] else []
        except Exception as e:
            logger.error("RAG component query error: %s", e)
            return []

    def retrieve_project_templates(self, query: str, n_results: int = 3) -> list[str]:
        """Return similar project templates for inspiration."""
        try:
            client = self._get_client()
            ef = self._embedding_fn()
            col = client.get_or_create_collection(PROJECTS_COLLECTION, embedding_function=ef)
            if col.count() == 0:
                self.seed_knowledge_base()
            result = col.query(query_texts=[query], n_results=min(n_results, col.count()))
            return result["documents"][0] if result["documents"] else []
        except Exception as e:
            logger.error("RAG project query error: %s", e)
            return []

    def get_context_for_project(self, input_data: dict) -> str:
        """Build a rich RAG context string for a project generation request."""
        query = (
            f"{input_data.get('category', '')} "
            f"{' '.join(input_data.get('components', []))} "
            f"{input_data.get('goal', '')}"
        )
        component_docs = self.retrieve_component_docs(query, n_results=6)
        template_docs = self.retrieve_project_templates(query, n_results=3)

        context_parts = []
        if component_docs:
            context_parts.append("## Relevant Component Knowledge\n" + "\n".join(f"- {d}" for d in component_docs))
        if template_docs:
            context_parts.append("## Similar Project Examples\n" + "\n".join(f"- {d}" for d in template_docs))

        return "\n\n".join(context_parts)


rag_service = RAGService()
