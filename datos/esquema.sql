-- Esquema para Postgres (Supabase). Generado desde app/db.py; la aplicación también crea las tablas al arrancar.

CREATE TABLE IF NOT EXISTS decisiones (
	id SERIAL NOT NULL, 
	solicitud_id INTEGER, 
	proyecto_id INTEGER, 
	vuelo_id INTEGER, 
	hotel_id INTEGER, 
	tarifa TEXT, 
	desglose TEXT, 
	total FLOAT, 
	motivo TEXT, 
	aprobado_por TEXT, 
	creado TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS documentos (
	id SERIAL NOT NULL, 
	nombre TEXT, 
	mime TEXT, 
	canal TEXT, 
	ruta TEXT, 
	huella TEXT, 
	creado TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS eventos (
	id SERIAL NOT NULL, 
	momento TEXT, 
	entidad TEXT, 
	entidad_id INTEGER, 
	paso TEXT, 
	detalle TEXT, 
	fuente TEXT, 
	duracion_ms INTEGER, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS gastos (
	id SERIAL NOT NULL, 
	documento_id INTEGER, 
	proyecto_id INTEGER, 
	viajero_id INTEGER, 
	comercio TEXT, 
	fecha TEXT, 
	categoria TEXT, 
	subtotal FLOAT, 
	impuesto FLOAT, 
	propina FLOAT, 
	total FLOAT, 
	moneda TEXT, 
	total_usd FLOAT, 
	metodo_pago TEXT, 
	canal_reserva TEXT, 
	confianza FLOAT, 
	estado TEXT, 
	alertas TEXT, 
	origen_dato TEXT, 
	creado TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS historial_ruta (
	id SERIAL NOT NULL, 
	busqueda TEXT, 
	origen TEXT, 
	destino TEXT, 
	fecha TEXT, 
	precio FLOAT, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS membresias (
	id SERIAL NOT NULL, 
	viajero_id INTEGER, 
	programa TEXT, 
	entidad TEXT, 
	estatus TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS observaciones (
	id SERIAL NOT NULL, 
	busqueda TEXT, 
	origen TEXT, 
	destino TEXT, 
	ida TEXT, 
	regreso TEXT, 
	aerolinea TEXT, 
	escalas INTEGER, 
	duracion_min FLOAT, 
	hora_salida FLOAT, 
	dia_semana INTEGER, 
	anticipacion INTEGER, 
	noches INTEGER, 
	precio FLOAT, 
	nivel_ruta TEXT, 
	tipico_min FLOAT, 
	tipico_max FLOAT, 
	capturado TEXT, 
	fuente TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS opciones (
	id SERIAL NOT NULL, 
	solicitud_id INTEGER, 
	tipo TEXT, 
	titulo TEXT, 
	precio FLOAT, 
	moneda TEXT, 
	datos TEXT, 
	tarifas TEXT, 
	origen_dato TEXT, 
	capturado TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS proyectos (
	id SERIAL NOT NULL, 
	nombre TEXT NOT NULL, 
	cliente TEXT, 
	ciudad TEXT, 
	fecha_inicio TEXT, 
	fecha_fin TEXT, 
	moneda TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS reglas (
	id SERIAL NOT NULL, 
	ambito TEXT, 
	entidad TEXT, 
	tarifa TEXT, 
	clave TEXT, 
	valor TEXT, 
	nota TEXT, 
	fuente TEXT, 
	confianza TEXT, 
	verificado TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS solicitudes (
	id SERIAL NOT NULL, 
	proyecto_id INTEGER, 
	viajero_id INTEGER, 
	origen TEXT, 
	destino TEXT, 
	ciudad TEXT, 
	ida TEXT, 
	regreso TEXT, 
	llegar_antes TEXT, 
	baterias_n INTEGER, 
	baterias_wh FLOAT, 
	maleta INTEGER, 
	prob_cambio FLOAT, 
	carro_dia FLOAT, 
	estado TEXT, 
	creado TEXT, 
	solicitado_por TEXT, 
	precio_min_buscador FLOAT, 
	costo_mas_barato FLOAT, 
	costo_mejor FLOAT, 
	ahorro_potencial FLOAT, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS viajeros (
	id SERIAL NOT NULL, 
	nombre TEXT NOT NULL, 
	base TEXT, 
	rol TEXT, 
	PRIMARY KEY (id)
);
