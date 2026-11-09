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
   pip install -r requirements.txt

4. Configurar las variables de entorno:
   Copiar el archivo `.env.example` y renombrarlo a `.env`. Definir los valores de las variables locales dentro del archivo. En local, `DATABASE_URL` puede quedar vacío para usar SQLite.

5. Aplicar las migraciones e iniciar el servidor de desarrollo:
   python manage.py migrate
   python manage.py runserver

## Gestión Finanzas

Gestión Finanzas registra y consulta ingresos y egresos en el mismo ledger `MovimientoFinanciero` que usa Gestión Publicidad, y permite clasificar esos movimientos con categorías financieras. El sitio ofrece pantallas propias para consultar y registrar movimientos y administrar sus categorías.

## Panel de gestión

La ruta `/` muestra el panel de Macaira Studio; las cuentas sin sesión ven el formulario propio de acceso y pueden autenticarse con su usuario o con un correo único asociado a la cuenta. «Recordarme siempre» conserva la sesión según `SESSION_COOKIE_AGE`; sin esa opción, la sesión vence al cerrar el navegador. Cerrar sesión invalida ambas modalidades.

El panel reúne trabajos, jornadas y tareas, insumos agrupados por área con variantes desplegables, trabajos por cobrar y finanzas, según los permisos de la cuenta. En Finanzas se pueden consultar movimientos por mes, con ingresos, egresos y saldo desglosados por moneda, sin conversiones. El calendario de jornadas muestra datos reales del sistema; las búsquedas de trabajos e insumos se ejecutan en el navegador sobre los datos cargados.

La interfaz propia permite consultar, crear, editar y eliminar trabajos, administrar jornadas con tareas y consumo de insumos, revisar cuentas por cobrar, gestionar inventario y variantes, reabastecer existencias y operar el ledger financiero. Las tareas se pueden marcar como completadas desde jornadas. Los módulos y acciones respetan los permisos de Django. Las rutas heredadas `/admin/` redirigen al panel de Macaira Studio; el Admin de Django no forma parte del flujo de usuario.

Para validar la instalación: `python manage.py check`, `python manage.py makemigrations --check --dry-run` y `python manage.py test`.