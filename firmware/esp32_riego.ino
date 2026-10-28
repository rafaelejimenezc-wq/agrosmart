/*
=============================================================================
 AgroSmart - Firmware ESP32 (Fase 2)
=============================================================================
 Lee un sensor capacitivo de humedad del suelo, envia la lectura al servidor
 de AgroSmart y enciende/apaga una bomba (o electrovalvula) por relé.

 Hardware sugerido:
   - ESP32 DevKit
   - Sensor capacitivo de humedad de suelo (analogico) -> GPIO 34
   - Modulo relé -> GPIO 26  (¡ojo con la logica invertida de algunos reles!)
   - Bomba/electrovalvula con fuente independiente y proteccion
   - Opcional: DHT22 -> GPIO 27 (temperatura)

 Antes de usar:
   1. Cambia SSID, PASSWORD y la IP de tu computador en SERVIDOR.
   2. Calibra SECO y MOJADO: mira el monitor serial con el sensor al aire
      y luego sumergido en agua, y pon esos valores.
   3. El telefono/ESP32 y el computador deben estar en la misma red Wi-Fi.

 Este sketch NO usa librerias externas (solo las del core de ESP32).
=============================================================================
*/

#include <WiFi.h>
#include <HTTPClient.h>

// ------------------------- Configuracion -----------------------------------
const char* SSID     = "TU_WIFI";
const char* PASSWORD = "TU_CLAVE";

// IP local del computador donde corre iot_server.py (no uses localhost aqui)
const char* SERVIDOR = "http://192.168.1.100:8000/api/lectura";
const char* DEVICE_ID = "esp32-01";

// Pines
const int PIN_HUMEDAD = 34;   // entrada analogica
const int PIN_RELE    = 26;   // salida al rele
const int PIN_DHT     = 27;   // opcional, no usado en este sketch base

// Calibracion del sensor (ajusta con el monitor serial)
const int SECO   = 4095;  // lectura con el sensor al aire
const int MOJADO = 1500;  // lectura con el sensor en agua

// Cada cuanto se envia una lectura (ms)
const unsigned long INTERVALO = 60000UL;

// ---------------------------------------------------------------------------
int leerHumedad() {
  long suma = 0;
  for (int i = 0; i < 8; i++) {
    suma += analogRead(PIN_HUMEDAD);
    delay(20);
  }
  int lectura = suma / 8;
  int porcentaje = map(lectura, SECO, MOJADO, 0, 100);
  porcentaje = constrain(porcentaje, 0, 100);
  return porcentaje;
}

void aplicarRiego(bool encender) {
  // Si tu rele se activa con LOW, invierte estas lineas.
  digitalWrite(PIN_RELE, encender ? HIGH : LOW);
  Serial.print("Bomba: ");
  Serial.println(encender ? "ENCENDIDA" : "APAGADA");
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_RELE, OUTPUT);
  aplicarRiego(false);

  Serial.print("Conectando a WiFi");
  WiFi.begin(SSID, PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Conectado. IP: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  int humedad = leerHumedad();
  Serial.print("Humedad: ");
  Serial.print(humedad);
  Serial.println(" %");

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(SERVIDOR);
    http.addHeader("Content-Type", "application/json");

    String cuerpo = "{\"device_id\":\"";
    cuerpo += DEVICE_ID;
    cuerpo += "\",\"humedad\":";
    cuerpo += String(humedad);
    cuerpo += "}";

    int codigo = http.POST(cuerpo);
    if (codigo > 0) {
      String respuesta = http.getString();
      Serial.print("Respuesta: ");
      Serial.println(respuesta);
      // Parseo simple para evitar dependencias externas.
      bool riego = respuesta.indexOf("\"riego\":true") >= 0;
      aplicarRiego(riego);
    } else {
      Serial.print("Error HTTP: ");
      Serial.println(codigo);
      aplicarRiego(false);  // seguridad: sin conexion, no regar
    }
    http.end();
  } else {
    Serial.println("WiFi desconectado. No se riega por seguridad.");
    aplicarRiego(false);
  }

  delay(INTERVALO);
}
