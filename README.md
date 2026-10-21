# Web de Gestión Financiera e Inventario para Macaira Studio

Sistema backend desarrollado con Python y Django para la administración centralizada de inventarios, órdenes de trabajo y control financiero de una empresa de publicidad.

## Tecnologías utilizadas

* Python 3
* Django Web Framework
* Python-Decouple (gestión de variables de entorno)
* SQLite (base de datos en entorno de desarrollo)
* PostgreSQL (base de datos en entorno de producción)

## Requisitos previos

* Python 3.10 o superior instalado en el sistema.
* Git para el control de versiones.

## Instrucciones de configuración local

1. Clonar el repositorio:
   git clone https://github.com/4a-r0n/MacairaStore.git
   cd MacairaStore

2. Crear y activar el entorno virtual:
   
   En Windows:
   python -m venv venv
   venv\Scripts\activate

   En Linux / macOS:
   python3 -m venv venv
   source venv/bin/activate

3. Instalar las dependencias del proyecto:
   pip install django python-decouple

4. Configurar las variables de entorno:
   Copiar el archivo `.env.example` y renombrarlo a `.env`. Definir los valores de las variables locales dentro del archivo.

5. Aplicar las migraciones e iniciar el servidor de desarrollo:
   python manage.py migrate
   python manage.py runserver