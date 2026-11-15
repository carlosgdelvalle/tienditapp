package mx.abarpay.mobile

// ---------------------------------------------------------------------------
// Datos SIMULADOS del modo demo: catálogo grande (~60), plantillas por tipo y
// tareas fijas. Sin red, sin dinero y sin datos de terceros.
// ---------------------------------------------------------------------------

/** Catálogo demo amplio: sirve para probar búsqueda, chips de categoría y LazyColumn. */
internal fun demoSeed(): List<Product> = listOf(
    // 1..12: los productos de siempre (las pruebas de venta dependen de sus precios).
    Product(1, "Coca-Cola 600 ml", "pieza", 1800, 24000, 5000, true, category = "Bebidas"),
    Product(2, "Sabritas sal 45 g", "pieza", 2200, 18000, 5000, true, category = "Botanas"),
    Product(3, "Pan Bimbo grande", "pieza", 4800, 6000, 5000, true, category = "Panadería"),
    Product(4, "Huevo (kg)", "kg", 4500, 10000, 5000, true, category = "Abarrotes"),
    Product(5, "Leche Lala 1 L", "pieza", 3100, 12000, 5000, true, category = "Lácteos"),
    Product(6, "Agua Bonafont 1 L", "pieza", 1500, 20000, 5000, true, category = "Bebidas"),
    Product(7, "Maruchan camarón", "pieza", 1600, 30000, 5000, true, category = "Abarrotes"),
    Product(8, "Gansito", "pieza", 1700, 15000, 5000, true, category = "Dulces"),
    Product(9, "Tortillas (kg)", "kg", 2600, 8000, 5000, false, category = "Tortillas"),
    Product(10, "Jabón Zote", "pieza", 2300, 9000, 5000, false, category = "Limpieza"),
    Product(11, "Galletas Marías", "pieza", 1900, 14000, 5000, false, category = "Botanas"),
    Product(12, "Fanta 600 ml", "pieza", 1700, 12000, 5000, false, category = "Bebidas"),
    Product(13, "Café soluble 100 g", "pieza", 4200, 7000, 5000, category = "Abarrotes"),
    Product(14, "Azúcar 1 kg", "kg", 2900, 15000, 5000, category = "Abarrotes"),
    Product(15, "Arroz 1 kg", "kg", 2700, 16000, 5000, category = "Abarrotes"),
    Product(16, "Frijol 1 kg", "kg", 3300, 11000, 5000, category = "Abarrotes"),
    Product(17, "Aceite 900 ml", "pieza", 4100, 8000, 5000, category = "Abarrotes"),
    Product(18, "Sal 1 kg", "kg", 1200, 9000, 5000, category = "Abarrotes"),
    Product(19, "Salsa catsup 400 g", "pieza", 2600, 6000, 5000, category = "Abarrotes"),
    Product(20, "Mayonesa 400 g", "pieza", 3400, 5000, 5000, category = "Abarrotes"),
    Product(21, "Atún en agua", "pieza", 2100, 14000, 5000, category = "Abarrotes"),
    Product(22, "Sardina en tomate", "pieza", 1800, 13000, 5000, category = "Abarrotes"),
    Product(23, "Chiles jalapeños", "pieza", 1500, 10000, 5000, category = "Abarrotes"),
    Product(24, "Sopa de pasta", "pieza", 1300, 17000, 5000, category = "Abarrotes"),
    Product(25, "Yogurt natural 1 L", "pieza", 3600, 7000, 5000, category = "Lácteos"),
    Product(26, "Queso panela 250 g", "pieza", 4500, 4000, 5000, category = "Lácteos"),
    Product(27, "Crema 200 ml", "pieza", 2200, 6000, 5000, category = "Lácteos"),
    Product(28, "Mantequilla 90 g", "pieza", 2400, 5000, 5000, category = "Lácteos"),
    Product(29, "Pan de caja chico", "pieza", 3200, 8000, 5000, category = "Panadería"),
    Product(30, "Bolillo (pieza)", "pieza", 300, 40000, 5000, category = "Panadería"),
    Product(31, "Concha de chocolate", "pieza", 900, 9000, 5000, category = "Panadería"),
    Product(32, "Donas glaseadas", "pieza", 1500, 7000, 5000, category = "Panadería"),
    Product(33, "Papel higiénico 4 rollos", "pieza", 4800, 5000, 5000, category = "Limpieza"),
    Product(34, "Detergente 1 kg", "pieza", 5200, 4500, 5000, category = "Limpieza"),
    Product(35, "Cloro 1 L", "pieza", 2100, 6000, 5000, category = "Limpieza"),
    Product(36, "Fabuloso 1 L", "pieza", 3900, 4000, 5000, category = "Limpieza"),
    Product(37, "Jabón de baño", "pieza", 1800, 11000, 5000, category = "Higiene"),
    Product(38, "Pasta dental", "pieza", 3200, 8000, 5000, category = "Higiene"),
    Product(39, "Shampoo 400 ml", "pieza", 5600, 3000, 5000, category = "Higiene"),
    Product(40, "Desodorante", "pieza", 4700, 3500, 5000, category = "Higiene"),
    Product(41, "Pañuelos desechables", "pieza", 1400, 12000, 5000, category = "Higiene"),
    Product(42, "Toallas sanitarias", "pieza", 3800, 5000, 5000, category = "Higiene"),
    Product(43, "Paletas de hielo", "pieza", 800, 20000, 5000, category = "Dulces"),
    Product(44, "Chocolates", "pieza", 1200, 16000, 5000, category = "Dulces"),
    Product(45, "Gomitas", "pieza", 1000, 18000, 5000, category = "Dulces"),
    Product(46, "Mazapán", "pieza", 700, 22000, 5000, category = "Dulces"),
    Product(47, "Palomitas microondas", "pieza", 1900, 9000, 5000, category = "Botanas"),
    Product(48, "Cacahuates salados", "pieza", 1100, 13000, 5000, category = "Botanas"),
    Product(49, "Refresco 2 L", "pieza", 3400, 8000, 5000, category = "Bebidas"),
    Product(50, "Jugo de naranja 1 L", "pieza", 3900, 6000, 5000, category = "Bebidas"),
    Product(51, "Agua mineral 600 ml", "pieza", 1800, 14000, 5000, category = "Bebidas"),
    Product(52, "Té frío 600 ml", "pieza", 2100, 10000, 5000, category = "Bebidas"),
    Product(53, "Bolsa de hielo 2 kg", "kg", 2500, 7000, 5000, category = "Bebidas"),
    Product(54, "Tortillas de harina (kg)", "kg", 3800, 5000, 5000, category = "Tortillas"),
    Product(55, "Totopos (paquete)", "paquete", 2800, 6000, 5000, category = "Botanas"),
    Product(56, "Torta de jamón", "pieza", 3500, 0, 5000, kind = KIND_PLATILLO, category = "Comida", unlimitedStock = true),
    Product(57, "Café de olla", "pieza", 2500, 0, 5000, kind = KIND_PLATILLO, category = "Comida", unlimitedStock = true),
    Product(58, "Corte de cabello", "servicio", 12000, 0, 5000, kind = KIND_SERVICIO, category = "Estética", unlimitedStock = true, durationMinutes = 30),
    Product(59, "Uñas de gel", "servicio", 18000, 0, 5000, kind = KIND_SERVICIO, category = "Estética", unlimitedStock = true, durationMinutes = 60),
    Product(60, "Lavado de tenis", "servicio", 9000, 0, 5000, kind = KIND_SERVICIO, category = "Servicios", unlimitedStock = true),
)

/** Una tarea de la plantilla por tipo de negocio (key estable para el servidor). */
internal data class TemplateTask(val key: String, val title: String)

/** Plantilla de tareas fija por tipo. Se crean sin asignar, como el servidor. */
internal fun demoTemplateTasks(typeKey: String): List<TemplateTask> = when (typeKey) {
    "tortilleria" -> listOf(
        TemplateTask("masa", "Revisar la masa del día"),
        TemplateTask("tortillas", "Contar tortillas vendidas"),
        TemplateTask("limpieza", "Limpiar la máquina tortilladora"),
    )
    "taqueria" -> listOf(
        TemplateTask("trompo", "Preparar el trompo de pastor"),
        TemplateTask("salsas", "Surtir salsas y limón"),
        TemplateTask("limpieza", "Limpiar la plancha"),
    )
    "comida-corrida" -> listOf(
        TemplateTask("menu", "Escribir el menú del día"),
        TemplateTask("guisados", "Revisar guisados disponibles"),
        TemplateTask("limpieza", "Limpiar mesas"),
    )
    "peluqueria" -> listOf(
        TemplateTask("citas", "Revisar citas del día"),
        TemplateTask("herramienta", "Desinfectar herramienta"),
        TemplateTask("limpieza", "Barrer el piso"),
    )
    "estetica" -> listOf(
        TemplateTask("citas", "Revisar citas del día"),
        TemplateTask("material", "Revisar material de uñas"),
        TemplateTask("limpieza", "Limpiar el área"),
    )
    "fondita" -> listOf(
        TemplateTask("menu", "Escribir el menú del día"),
        TemplateTask("insumos", "Revisar insumos de la cocina"),
        TemplateTask("limpieza", "Limpiar la cocina"),
    )
    "otro" -> listOf(
        TemplateTask("apertura", "Abrir el negocio"),
        TemplateTask("inventario", "Contar inventario"),
        TemplateTask("limpieza", "Limpiar el local"),
    )
    else -> listOf(
        TemplateTask("inventario", "Contar inventario"),
        TemplateTask("limpieza", "Limpiar tienda"),
        TemplateTask("caducidad", "Revisar fechas de caducidad"),
        TemplateTask("anaquel", "Acomodar anaquel"),
    )
}

/** Plantilla de catálogo por tipo: el demo la reproduce sin red. */
internal fun demoTemplateItems(typeKey: String): List<Product> = when (typeKey) {
    "tiendita" -> demoSeed().take(24).mapIndexed { index, product ->
        product.copy(id = index + 1, stockMilli = if (product.unlimitedStock) 0 else product.stockMilli)
    }
    "tortilleria" -> listOf(
        Product(1, "Tortillas de maíz (kg)", "kg", 2600, 20000, 5000, true, category = "Tortillas"),
        Product(2, "Tortillas de harina (kg)", "kg", 3800, 12000, 5000, true, category = "Tortillas"),
        Product(3, "Masa para tamales (kg)", "kg", 3000, 8000, 5000, category = "Masa"),
        Product(4, "Totopos (paquete)", "paquete", 2800, 6000, 5000, category = "Botanas"),
        Product(5, "Tostadas (paquete)", "paquete", 2200, 9000, 5000, category = "Botanas"),
        Product(6, "Sopes (pieza)", "pieza", 450, 15000, 5000, category = "Antojitos"),
    )
    "taqueria" -> listOf(
        Product(1, "Taco de pastor", "pieza", 1500, 0, 5000, true, kind = KIND_PLATILLO, category = "Tacos", unlimitedStock = true),
        Product(2, "Taco de suadero", "pieza", 1600, 0, 5000, true, kind = KIND_PLATILLO, category = "Tacos", unlimitedStock = true),
        Product(3, "Gringa", "pieza", 4500, 0, 5000, kind = KIND_PLATILLO, category = "Tacos", unlimitedStock = true),
        Product(4, "Orden de tacos (combo)", "combo", 9000, 0, 5000, kind = KIND_PLATILLO, category = "Tacos", unlimitedStock = true),
        Product(5, "Refresco 600 ml", "pieza", 1800, 12000, 5000, category = "Bebidas"),
        Product(6, "Agua fresca (litro)", "litro", 3000, 0, 5000, kind = KIND_PLATILLO, category = "Bebidas", unlimitedStock = true),
    )
    "comida-corrida" -> listOf(
        Product(1, "Comida corrida (combo)", "combo", 8500, 0, 5000, true, kind = KIND_PLATILLO, category = "Comida corrida", unlimitedStock = true),
        Product(2, "Sopa del día", "pieza", 3000, 0, 5000, kind = KIND_PLATILLO, category = "Entradas", unlimitedStock = true),
        Product(3, "Guisado del día", "pieza", 5500, 0, 5000, kind = KIND_PLATILLO, category = "Guisados", unlimitedStock = true),
        Product(4, "Agua fresca (litro)", "litro", 3000, 0, 5000, kind = KIND_PLATILLO, category = "Bebidas", unlimitedStock = true),
        Product(5, "Postre del día", "pieza", 2500, 0, 5000, kind = KIND_PLATILLO, category = "Postres", unlimitedStock = true),
    )
    "peluqueria" -> listOf(
        Product(1, "Corte de cabello", "servicio", 12000, 0, 5000, true, kind = KIND_SERVICIO, category = "Cortes", unlimitedStock = true, durationMinutes = 30),
        Product(2, "Corte y barba", "servicio", 16000, 0, 5000, kind = KIND_SERVICIO, category = "Cortes", unlimitedStock = true, durationMinutes = 45),
        Product(3, "Barba", "servicio", 6000, 0, 5000, kind = KIND_SERVICIO, category = "Barba", unlimitedStock = true, durationMinutes = 20),
        Product(4, "Tinte", "servicio", 25000, 0, 5000, kind = KIND_SERVICIO, category = "Color", unlimitedStock = true, durationMinutes = 90),
        Product(5, "Lavado y peinado", "servicio", 5000, 0, 5000, kind = KIND_SERVICIO, category = "Cortes", unlimitedStock = true, durationMinutes = 20),
    )
    "estetica" -> listOf(
        Product(1, "Manicure", "servicio", 10000, 0, 5000, true, kind = KIND_SERVICIO, category = "Uñas", unlimitedStock = true, durationMinutes = 45),
        Product(2, "Pedicure", "servicio", 12000, 0, 5000, kind = KIND_SERVICIO, category = "Uñas", unlimitedStock = true, durationMinutes = 60),
        Product(3, "Uñas de gel", "servicio", 18000, 0, 5000, kind = KIND_SERVICIO, category = "Uñas", unlimitedStock = true, durationMinutes = 60),
        Product(4, "Uñas acrílicas", "servicio", 22000, 0, 5000, kind = KIND_SERVICIO, category = "Uñas", unlimitedStock = true, durationMinutes = 90),
        Product(5, "Retiro de uñas", "servicio", 5000, 0, 5000, kind = KIND_SERVICIO, category = "Uñas", unlimitedStock = true, durationMinutes = 30),
    )
    "fondita" -> listOf(
        Product(1, "Comida corrida (combo)", "combo", 7500, 0, 5000, true, kind = KIND_PLATILLO, category = "Comida", unlimitedStock = true),
        Product(2, "Quesadilla", "pieza", 3000, 0, 5000, kind = KIND_PLATILLO, category = "Antojitos", unlimitedStock = true),
        Product(3, "Taco dorado", "pieza", 1500, 0, 5000, kind = KIND_PLATILLO, category = "Antojitos", unlimitedStock = true),
        Product(4, "Café de olla", "pieza", 2000, 0, 5000, kind = KIND_PLATILLO, category = "Bebidas", unlimitedStock = true),
        Product(5, "Agua fresca (litro)", "litro", 2500, 0, 5000, kind = KIND_PLATILLO, category = "Bebidas", unlimitedStock = true),
    )
    else -> listOf(
        Product(1, "Producto de ejemplo", "pieza", 2500, 12000, 5000, true, category = "General"),
        Product(2, "Servicio de ejemplo", "servicio", 15000, 0, 5000, kind = KIND_SERVICIO, category = "Servicios", unlimitedStock = true, durationMinutes = 60),
        Product(3, "Platillo de ejemplo", "pieza", 5500, 0, 5000, kind = KIND_PLATILLO, category = "Comida", unlimitedStock = true),
    )
}
