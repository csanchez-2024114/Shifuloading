/* Genera src/plantillas/catalogos/iconos.js (D32): ~400 conceptos de CRM → el ícono REAL de cada familia de react-icons,
 * con todos sus estilos. Ningún nombre se escribe a mano en el catálogo: se buscan en los index.d.ts instalados, así que
 * todo lo que sale existe. Uso (desde la raíz de Shifuloading): node laboratorio/servidor/generar-iconos.mjs */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'

const nombres = (fam) => new Set([...readFileSync(`node_modules/react-icons/${fam}/index.d.ts`, 'utf8').matchAll(/export declare const (\w+)/g)].map((m) => m[1]))
const F = Object.fromEntries(['lu', 'tb', 'pi', 'hi2', 'md', 'fa6', 'ri'].map((f) => [f, nombres(f)]))

export const FAMILIAS = {
  lu: { nombre: 'Lucide', estilos: ['linea'], nota: 'trazo fino y parejo (el del CRM hoy)' },
  tb: { nombre: 'Tabler', estilos: ['linea', 'relleno'], nota: 'trazo redondeado, muy completo' },
  pi: { nombre: 'Phosphor', estilos: ['normal', 'thin', 'light', 'bold', 'fill', 'duotone'], nota: '6 grosores: del más fino al de dos tonos' },
  hi2: { nombre: 'Heroicons', estilos: ['linea', 'solido'], nota: 'el de Tailwind: sobrio' },
  md: { nombre: 'Material', estilos: ['solido', 'linea', 'redondo', 'recto'], nota: 'el de Google: geométrico' },
  fa6: { nombre: 'Font Awesome', estilos: ['solido', 'regular'], nota: 'grueso y reconocible' },
  ri: { nombre: 'Remix', estilos: ['linea', 'relleno'], nota: 'equilibrado, buen par línea/relleno' },
}

// concepto: nombres base en inglés (PascalCase, estilo Lucide), del más preciso al más general.
const CONCEPTOS = `
inicio:House|Home|LayoutDashboard; tablero:LayoutDashboard|Dashboard|Kanban|Columns; menu:Menu|List; ajustes:Settings|Gear|Cog; buscar:Search|MagnifyingGlass; filtro:Filter|Funnel|ListFilter
contactos:Users|UsersThree|Contact|People; cliente:User|UserCircle|Person; clientes-vip:Crown|Star; nuevo-cliente:UserPlus|UserAdd|PersonAdd; quitar-cliente:UserMinus|UserX|UserRemove; perfil:CircleUser|UserCircle|IdCard
empresa:Building2|Building|Buildings|Office|Business; tienda:Store|Storefront|Shop; fabrica:Factory; sucursal:MapPin|Location|Place; equipo:UsersRound|Users|Team|Group; organigrama:Network|TreeStructure|Sitemap
ventas:TrendingUp|ChartLineUp|TrendUp; embudo:Filter|Funnel; oportunidad:Target|Crosshair; trato:Handshake|HandshakeSimple; propuesta:FileText|Article|Description; cotizacion:FileSpreadsheet|Receipt|Calculator
factura:Receipt|ReceiptText|Invoice|FileInvoice; cobro:HandCoins|Coins|CashStack|Money; pago:CreditCard|Payment|Wallet; dinero:Banknote|Money|Cash|CurrencyDollar; billetera:Wallet; banco:Landmark|Bank|Bank2
descuento:Percent|BadgePercent|Discount|Tag; precio:Tag|PriceTag|Tags; carrito:ShoppingCart|Cart|ShoppingCartSimple; bolsa:ShoppingBag|Bag|Handbag; pedido:Package|ClipboardList|Order; regalo:Gift
inventario:Boxes|Package|Warehouse|Archive; producto:Package2|Box|Cube|Package; almacen:Warehouse; codigo-barras:Barcode|ScanBarcode; qr:QrCode; proveedor:Truck|Factory|Supplier
envio:Truck|Shipping|LocalShipping; entrega:PackageCheck|Delivery|TruckDelivery; ruta:Route|Path|Map; mapa:Map|MapTrifold|MapPinned; ubicacion:MapPin|Location|Place; vehiculo:Car|CarSimple|DirectionsCar
agenda:CalendarDays|Calendar|CalendarBlank|Event; cita:CalendarCheck|CalendarCheck2|EventAvailable; calendario:Calendar|CalendarBlank; hora:Clock|Time|Schedule; recordatorio:Bell|BellRing|Alarm|Notification; alarma:AlarmClock|Alarm
vencimiento:Hourglass|Timer|CalendarX|Clock; urgente:Siren|AlertTriangle|Warning|TriangleAlert; tarea:SquareCheck|CheckSquare|Task|ListChecks; lista-tareas:ListTodo|ListChecks|Checklist|ClipboardCheck; hecho:CircleCheck|CheckCircle|Check; pendiente:CircleDashed|Circle|Pending
proyecto:FolderKanban|Kanban|Folder|Briefcase; campana:Megaphone|Campaign|Speakerphone; hito:Flag|Milestone; meta:Target|Goal|Trophy; logro:Trophy|Award|Medal; progreso:Gauge|Speedometer|ChartPie
nota:StickyNote|Note|Notepad|NotebookPen; documento:File|FileText|Document; carpeta:Folder|FolderOpen; archivo:Archive|FileArchive; adjunto:Paperclip|Attachment; contrato:FileSignature|Signature|Contract|PenLine
correo:Mail|Envelope|Email; enviar:Send|PaperPlane|PaperPlaneTilt; bandeja:Inbox|Tray; whatsapp:MessageCircle|WhatsappLogo|Whatsapp|Chat; chat:MessagesSquare|ChatsCircle|Chat|Message; mensaje:MessageSquare|ChatText|Comment
llamada:Phone|PhoneCall|Call; telefono:Smartphone|DeviceMobile|PhoneIphone|Mobile; videollamada:Video|VideoCamera|Videocam; microfono:Mic|Microphone; altavoz:Volume2|SpeakerHigh|VolumeUp; auriculares:Headphones|Headset
reporte:FileChartColumn|ChartBar|Report|Assessment; grafica:ChartColumn|ChartBar|BarChart|ChartBarHorizontal; grafica-linea:ChartLine|LineChart|ShowChart|ChartLineUp; grafica-dona:ChartPie|PieChart|DonutLarge|ChartDonut; tendencia-sube:TrendingUp|TrendUp|ArrowTrendUp; tendencia-baja:TrendingDown|TrendDown|ArrowTrendDown
estadistica:Activity|Pulse|Analytics; medidor:Gauge|Speedometer; tabla:Table|Table2|TableProperties|GridOn; cuadricula:Grid3x3|LayoutGrid|GridFour|Grid; columnas:Columns3|Columns|ViewColumn; filas:Rows3|Rows|TableRows
historial:History|ClockCounterClockwise|Restore; actividad:Activity|Pulse|Timeline; linea-tiempo:GitCommitHorizontal|Timeline|ChartTimeline; automatizacion:Zap|Lightning|Bolt|Automation; flujo:Workflow|FlowArrow|GitBranch|AccountTree; integracion:Plug|Puzzle|PuzzlePiece|Extension
robot:Bot|Robot|SmartToy; ia:Sparkles|Sparkle|AutoAwesome|MagicWand; idea:Lightbulb|Bulb; ayuda:CircleHelp|HelpCircle|Question|Help; info:Info|InfoCircle; alerta:TriangleAlert|AlertTriangle|Warning
seguridad:Shield|ShieldCheck|Security; candado:Lock|LockKey|LockSimple; abierto:LockOpen|Unlock|LockSimpleOpen; llave:Key|KeyRound|VpnKey; contrasena:KeyRound|Password|Asterisk; huella:Fingerprint
salud:HeartPulse|Heartbeat|Health; hospital:Hospital|LocalHospital|FirstAid; doctor:Stethoscope|MedicalServices|Doctor; medicina:Pill|Pills|Medication|Capsule; diente:Smile|Tooth|Dental; jeringa:Syringe|Vaccines
gimnasio:Dumbbell|Barbell|FitnessCenter; deporte:Trophy|SoccerBall|Basketball|SportsSoccer; bicicleta:Bike|Bicycle|PedalBike; correr:Footprints|PersonSimpleRun|DirectionsRun|Run; yoga:PersonStanding|Flower|SelfImprovement; agua:Droplet|Drop|WaterDrop
restaurante:UtensilsCrossed|ForkKnife|Restaurant|Utensils; cafe:Coffee|LocalCafe|Cup; bebida:Wine|Beer|LocalBar|Martini; pastel:Cake|CakeSlice|Cake2; pizza:Pizza|LocalPizza; cocina:ChefHat|CookingPot|Kitchen
hotel:Hotel|Bed|BedDouble|LocalHotel; cama:BedDouble|Bed|BedSingle; maleta:Luggage|Suitcase|BriefcaseBusiness; avion:Plane|Airplane|Flight; viaje:PlaneTakeoff|AirplaneTakeoff|TravelExplore; playa:Palmtree|TreePalm|BeachAccess|Umbrella
escuela:School|GraduationCap|Student; libro:Book|BookOpen|MenuBook; alumno:GraduationCap|Student|School; clase:Presentation|ChalkboardTeacher|Class; certificado:Award|Certificate|Badge; lapiz:Pencil|PencilSimple|Edit
casa:House|Home; inmueble:Building|Buildings|Apartment|HomeWork; llave-casa:KeyRound|Key; construccion:HardHat|Construction|Hammer|Crane; herramienta:Wrench|Tool|Build|Hammer; pintura:Paintbrush|PaintBrush|Brush|FormatPaint
auto:Car|CarSimple|DirectionsCar; taller:Wrench|Garage|CarRepair; gasolina:Fuel|GasPump|LocalGasStation; llanta:CircleDot|Tire|Disc; bateria:Battery|BatteryFull|BatteryCharging; motor:Cog|Engine|Settings
belleza:Sparkles|Sparkle|Spa|FaceSmile; tijeras:Scissors|ContentCut; espejo:ScanFace|Mirror|Face; perfume:SprayCan|FlaskConical|Flask; manicura:HandHeart|Hand|PanTool; spa:Flower2|Flower|Spa|FlowerLotus
mascota:PawPrint|Pets|Paw; perro:Dog; gato:Cat; veterinaria:Stethoscope|Syringe|PawPrint; hueso:Bone; pez:Fish
camara:Camera|PhotoCamera; foto:Image|ImageSquare|Photo; galeria:Images|ImagesSquare|PhotoLibrary|Collections; video:Video|Film|Videocam|Movie; musica:Music|MusicNote|MusicNotes; evento:PartyPopper|Confetti|Celebration|Calendar
abogado:Scale|Gavel|Balance|Scales; ley:Gavel|Hammer|Scale; seguro:ShieldCheck|Umbrella|HealthAndSafety; contabilidad:Calculator|Calculate; impuesto:Percent|ReceiptText|Receipt; firma:Signature|PenLine|Draw
donacion:HandHeart|HeartHandshake|VolunteerActivism|Heart; voluntario:HandHelping|Handshake|VolunteerActivism; comunidad:Users|UsersThree|Groups; corazon:Heart|Favorite; planeta:Globe|GlobeHemisphereWest|Public|Earth; hoja:Leaf|Eco|Plant
software:Code|CodeSimple|Terminal; servidor:Server|Storage|Database; nube:Cloud|CloudUpload; base-datos:Database|Storage; usuario-tecnico:UserCog|UserGear|ManageAccounts; error:Bug|BugBeetle|BugReport
web:Globe|Browser|Language|Web; enlace:Link|Link2|LinkSimple; compartir:Share2|Share|ShareNetwork; descargar:Download|DownloadSimple|FileDownload; subir:Upload|UploadSimple|FileUpload; nube-subir:CloudUpload|CloudArrowUp
agregar:Plus|PlusCircle|Add; quitar:Minus|MinusCircle|Remove; borrar:Trash2|Trash|Delete; editar:Pencil|PencilSimple|Edit|PenLine; guardar:Save|FloppyDisk|SaveAlt; copiar:Copy|ContentCopy
deshacer:Undo2|Undo|ArrowCounterClockwise; rehacer:Redo2|Redo|ArrowClockwise; refrescar:RefreshCw|ArrowsClockwise|Refresh; sincronizar:RefreshCcw|ArrowsCounterClockwise|Sync; cerrar:X|Close|XCircle; aceptar:Check|CheckCircle|Done
flecha-derecha:ArrowRight|ArrowForward|CaretRight; flecha-izquierda:ArrowLeft|ArrowBack|CaretLeft; flecha-arriba:ArrowUp|ArrowUpward|CaretUp; flecha-abajo:ArrowDown|ArrowDownward|CaretDown; expandir:Maximize2|Expand|Fullscreen|ArrowsOut; contraer:Minimize2|ArrowsIn|FullscreenExit
ojo:Eye|Visibility; ocultar:EyeOff|EyeSlash|VisibilityOff; estrella:Star|StarOutline; favorito:Heart|Bookmark|Favorite; marcador:Bookmark|BookmarkSimple; etiqueta:Tag|Tags|Label|Sell
campana-aviso:Bell|BellSimple|Notifications; silencio:BellOff|BellSlash|NotificationsOff; reloj-arena:Hourglass|HourglassMedium|HourglassEmpty; cronometro:Timer|Stopwatch; fuego:Flame|Fire|LocalFireDepartment; rayo:Zap|Lightning|Bolt
sol:Sun|LightMode; luna:Moon|DarkMode; tema:Palette|PaletteOutline|ColorLens; color:Palette|Pipette|EyeDropper|Colorize; tipografia:Type|TextAa|TextFields|Typography; imagen-marca:Image|ImageSquare|Brand
logo:Hexagon|Shapes|Polygon; diseno:PenTool|PenNib|DesignServices|Brush; capas:Layers|Stack|LayersTriple; plantilla:LayoutTemplate|Template|Dashboard; pieza:Puzzle|PuzzlePiece|Extension; bloque:Square|SquareSimple|CropSquare
mover:Move|ArrowsOutCardinal|OpenWith; arrastrar:GripVertical|DotsSixVertical|DragIndicator; ordenar:ArrowUpDown|ArrowsDownUp|SortAscending|Sort; ordenar-az:ArrowDownAZ|SortAscending|SortByAlpha; tamano:Scaling|Resize|AspectRatio; alinear:AlignLeft|TextAlignLeft|FormatAlignLeft
codigo:Code|CodeSimple; terminal:Terminal|TerminalWindow; pantalla:Monitor|Desktop|DesktopWindows; laptop:Laptop|LaptopMac; tableta:Tablet|DeviceTablet|TabletMac; impresora:Printer|Print
wifi:Wifi|WifiHigh; bluetooth:Bluetooth; bateria-baja:BatteryLow|BatteryWarning; enchufe:Plug|Power|PowerPlug; encender:Power|PowerSettingsNew; senal:Signal|CellSignalFull|SignalCellularAlt
usuario-check:UserCheck|UserCircleCheck|HowToReg; usuario-x:UserX|UserCircleMinus|PersonOff; usuarios-grupo:UsersRound|UsersFour|Diversity3|Groups; bebe:Baby|BabyCarriage|ChildCare; nino:Baby|Child|ChildFriendly; anciano:PersonStanding|Elderly|Accessibility
accesibilidad:Accessibility|Wheelchair; idioma:Languages|Translate|Language; mundo:Globe|Earth|Public; brujula:Compass|Explore; bandera:Flag|FlagBanner; casa-ubicacion:MapPinHouse|HouseLine|Home
puntuacion:Star|StarHalf|Grade; resena:MessageSquareQuote|ChatCenteredText|RateReview|Quote; encuesta:ClipboardList|ListChecks|Poll|Survey; votar:Vote|HowToVote|ThumbsUp; me-gusta:ThumbsUp|ThumbUp|Like; no-me-gusta:ThumbsDown|ThumbDown|Dislike
suscripcion:Repeat|Repeat1|Autorenew|Loop; membresia:IdCard|IdentificationCard|CardMembership|Badge; tarjeta:CreditCard|Card; pase:Ticket|Tickets|ConfirmationNumber; boleto:Ticket|TicketCheck|LocalActivity; vale:TicketPercent|Coupon|LocalOffer
grafica-area:ChartArea|AreaChart|ChartLine; grafica-dispersion:ChartScatter|ScatterPlot|ChartScatter; grafica-gantt:ChartGantt|GanttChart|Timeline; mapa-calor:Grid3x3|SquaresFour|GridOn; kpi:Gauge|Target|Speed; porcentaje:Percent|Percentage
reloj:Clock|Clock3|Schedule; fecha:Calendar|Today|CalendarToday; semana:CalendarRange|CalendarDots|DateRange; mes:CalendarDays|CalendarMonth|Calendar; ano:CalendarFold|CalendarBlank|Event; cumpleanos:Cake|CakeSlice|Celebration
lluvia:CloudRain|CloudRain|Umbrella; nieve:Snowflake|AcUnit; temperatura:Thermometer|Thermostat|DeviceThermostat; viento:Wind|Air; arbol:TreePine|Tree|Park; flor:Flower|Flower2|LocalFlorist
dinero-entrada:ArrowDownToLine|ArrowDownLeft|CallReceived|Download; dinero-salida:ArrowUpFromLine|ArrowUpRight|CallMade|Upload; balance:Scale|Scales|Balance; ahorro:PiggyBank|Savings; credito:Landmark|CreditCard|AccountBalance; caja:Vault|Safe|Inventory2

caja-registradora:Calculator|CashRegister|PointOfSale; recibo:Receipt|ReceiptText|ReceiptLong; ticket-venta:ReceiptText|Receipt; moneda:Coins|Coin|CurrencyCircleDollar; euro:Euro|CurrencyEur; quetzal:Banknote|Money|Payments
transferencia:ArrowLeftRight|ArrowsLeftRight|SwapHoriz|ArrowsExchange; reembolso:Undo2|ArrowUUpLeft|AssignmentReturn|ArrowBackUp; deuda:CircleAlert|WarningCircle|ErrorOutline|AlertCircle; credito-tarjeta:CreditCard|Cards|CreditCardMultiple; presupuesto:ChartPie|PiggyBank|Savings; gasto:ArrowDownRight|TrendDown|MoneyOff
cliente-nuevo:UserRoundPlus|UserPlus|PersonAdd; clientes-grupo:Users|UsersThree|Groups; contacto-libreta:BookUser|AddressBook|ContactPage|Contacts; tarjeta-visita:Contact|IdCard|ContactMail; cumpleanos-cliente:Gift|Cake; lealtad:Award|Medal|Loyalty|Heart
prospecto:UserSearch|UserFocus|PersonSearch; lead:Magnet|MagnetStraight; seguimiento:CalendarClock|ClockClockwise|Update|Clock; contactar:PhoneOutgoing|PhoneOutgoing|PhoneForwarded; perdido:CircleX|XCircle|Cancel; ganado:BadgeCheck|SealCheck|Verified|CircleCheck
estado:CircleDot|Circle|RadioButtonChecked; prioridad:ArrowUpWideNarrow|ArrowFatLinesUp|PriorityHigh|Flag; asignar:UserCheck|UserCircleCheck|AssignmentInd; responsable:UserCog|UserGear|ManageAccounts; etapa:Milestone|Steps|LinearScale|Layers; columna-kanban:Columns2|Columns|ViewColumn|Kanban
correo-enviado:MailCheck|EnvelopeSimpleOpen|MarkEmailRead; correo-abierto:MailOpen|EnvelopeOpen|Drafts; plantilla-correo:MailPlus|EnvelopeSimple|Email; boletin:Newspaper|Article|Feed; sms:MessageSquareText|ChatText|Sms|Message; notificacion-push:BellDot|BellRinging|NotificationsActive
instagram:Instagram|InstagramLogo; facebook:Facebook|FacebookLogo; youtube:Youtube|YoutubeLogo; linkedin:Linkedin|LinkedinLogo; twitter:Twitter|TwitterLogo; tiktok:Music2|TiktokLogo|Tiktok
redes-sociales:Share2|ShareNetwork|Share; publicacion:Newspaper|Article|PostAdd; anuncio:Megaphone|Speakerphone|Campaign; audiencia:UsersRound|Users|Groups; alcance:Radar|Broadcast|Sensors; clic:MousePointerClick|Cursor|Mouse
reunion:Presentation|UsersThree|Groups; presentacion:Presentation|PresentationChart|SlideshowOutline|Slideshow; pizarra:Presentation|Chalkboard|Whiteboard; agenda-reunion:CalendarClock|CalendarPlus|EventNote; sala:DoorOpen|Door|MeetingRoom; visita:Footprints|Footprints|DirectionsWalk
turno:CalendarClock|Clock|Schedule; fila-espera:ListOrdered|ListNumbers|FormatListNumbered; reservar:CalendarPlus|CalendarPlus|EventAvailable; cancelar-cita:CalendarX|CalendarX|EventBusy; confirmar-cita:CalendarCheck|CalendarCheck|EventAvailable; no-asistio:UserX|UserMinus|PersonOff
historia-clinica:ClipboardPlus|ClipboardText|Assignment; receta:FileHeart|Prescription|Receipt; laboratorio:FlaskConical|Flask|Science; radiografia:ScanLine|Scan|Radiology; ambulancia:Ambulance|FirstAidKit|LocalHospital; paciente:UserRound|User|PersonalInjury
clase-grupal:Users|UsersFour|Groups; entrenador:Dumbbell|Barbell|SportsGymnastics; rutina:ListChecks|ListBullets|FitnessCenter; asistencia:ClipboardCheck|CheckSquare|FactCheck; peso:Weight|Scale|MonitorWeight; nutricion:Apple|Carrot|Restaurant
menu-comida:Utensils|ForkKnife|RestaurantMenu|MenuBook; mesa:Armchair|Chair|TableRestaurant|TableBar; reserva-mesa:Armchair|CalendarCheck; delivery:Bike|Moped|DeliveryDining|Motorcycle; propina:HandCoins|Coins; cocinero:ChefHat|CookingPot
habitacion:BedDouble|Bed|Hotel; check-in:LogIn|SignIn|Login; check-out:LogOut|SignOut|Logout; limpieza:Sparkles|Broom|CleaningServices; llave-hotel:KeyRound|Key|VpnKey; desayuno:Croissant|Coffee|FreeBreakfast
curso:BookOpen|BookOpenText|School; examen:FileCheck|Exam|Quiz; calificacion:BadgeCheck|Star|Grade; horario:CalendarRange|CalendarDots|Schedule; profesor:Presentation|ChalkboardTeacher|PersonPin; matricula:ClipboardPen|ClipboardText|AppRegistration
obra:HardHat|Crane|Construction; plano:Ruler|Blueprint|Architecture|Compass; material:Brick|Cube|Inventory; presupuesto-obra:Calculator|Calculate; cuadrilla:Users|UsersThree|Engineering; avance:ChartNoAxesColumnIncreasing|ChartBar|TrendingUp
reparacion:Wrench|Wrench|Build; diagnostico:Search|MagnifyingGlass|Troubleshoot; repuesto:Cog|Gear|Settings; orden-trabajo:ClipboardList|ClipboardText|Assignment; garantia:ShieldCheck|ShieldCheck|VerifiedUser; mecanico:Wrench|Toolbox|Handyman
propiedad:House|HouseLine|Home; alquiler:KeyRound|Key; venta-casa:Signpost|SignpostBig|Sell|Tag; visita-casa:DoorOpen|Door|SensorDoor; metros:Ruler|Straighten; hipoteca:Landmark|Bank|AccountBalance
poliza:FileBadge|FileText|Policy|Description; siniestro:CarFront|Car|CarCrash; beneficiario:UserHeart|HeartHandshake|FamilyRestroom|Users; renovacion:RefreshCw|ArrowsClockwise|Autorenew; cobertura:Umbrella|Shield; riesgo:TriangleAlert|Warning|Report
expediente:FolderOpen|FolderSimple|FolderShared|Folder; audiencia-legal:Gavel|Gavel; plazo:CalendarClock|Timer|Schedule; honorarios:Banknote|Money|Payments; demanda:FileWarning|FileX|Report; tribunal:Landmark|Bank|AccountBalance
sesion-foto:Camera|Aperture|CameraAlt; album:BookImage|Images|PhotoAlbum|PhotoLibrary; edicion-foto:SlidersHorizontal|Sliders|Tune; boda:Gem|Diamond|Heart; dron:Plane|Drone|FlightTakeoff; iluminacion:Lamp|Lightbulb|LightMode
donante:HandHeart|HeartHandshake|VolunteerActivism; campana-recaudacion:Megaphone|Target|Campaign; beneficiado:HeartHandshake|Users; impacto:Sparkles|ChartLineUp|Insights; voluntariado:HandHelping|Handshake; transparencia:Eye|Visibility
suscriptor:UserCheck|UserCircleCheck|HowToReg; plan:Layers|Stack|ViewModule; licencia:KeySquare|Key|VpnKey|Key; soporte:LifeBuoy|Lifebuoy|SupportAgent|Headset; ticket-soporte:Ticket|TicketCheck|ConfirmationNumber; version:GitBranch|GitBranch|AccountTree
envio-paquete:PackageOpen|Package|LocalShipping; rastreo:Radar|Crosshair|GpsFixed|Navigation; repartidor:Bike|Truck|DeliveryDining; guia:FileText|Article|Description; aduana:Stamp|Seal|Approval; flota:TruckElectric|Truck|LocalShipping
mostrador:Store|Storefront|Store; catalogo:BookOpen|Books|LibraryBooks; oferta:BadgePercent|Percent|LocalOffer; devolucion:PackageX|ArrowUUpLeft|AssignmentReturn; resena-producto:Star|StarHalf|RateReview; stock-bajo:PackageMinus|Warning|Inventory
`.trim().split(/[;\n]/).map((x) => x.trim()).filter(Boolean).map((x) => { const [c, n] = x.split(':'); return [c.trim(), n.split('|').map((s) => s.trim())] })

/** El nombre real en cada familia (o null). Prueba cada nombre base con las convenciones de la familia. */
function buscar(fam, bases) {
  const S = F[fam], hay = (n) => (S.has(n) ? n : null)
  for (const b of bases) {
    switch (fam) {
      case 'lu': { const n = hay(`Lu${b}`); if (n) return n; break }
      case 'tb': { const l = hay(`Tb${b}`); if (l) return { linea: l, ...(hay(`Tb${b}Filled`) ? { relleno: `Tb${b}Filled` } : {}) }; break }
      case 'pi': { const n = hay(`Pi${b}`); if (n) { const o = { normal: n }; for (const [k, s] of [['thin', 'Thin'], ['light', 'Light'], ['bold', 'Bold'], ['fill', 'Fill'], ['duotone', 'Duotone']]) if (hay(`Pi${b}${s}`)) o[k] = `Pi${b}${s}`; return o } break }
      case 'hi2': { const l = hay(`HiOutline${b}`); if (l) return { linea: l, ...(hay(`Hi${b}`) ? { solido: `Hi${b}` } : {}) }; break }
      case 'md': { const s = hay(`Md${b}`) || hay(`MdOutline${b}`); if (s) { const o = { solido: s }; for (const [k, p] of [['linea', 'MdOutline'], ['redondo', 'MdRound'], ['recto', 'MdSharp']]) if (hay(`${p}${b}`)) o[k] = `${p}${b}`; return o } break }
      case 'fa6': { const s = hay(`Fa${b}`) || hay(`FaReg${b}`); if (s) return { solido: s, ...(hay(`FaReg${b}`) ? { regular: `FaReg${b}` } : {}) }; break }
      case 'ri': { const l = hay(`Ri${b}Line`); if (l) return { linea: l, ...(hay(`Ri${b}Fill`) ? { relleno: `Ri${b}Fill` } : {}) }; break }
    }
  }
  return null
}

const iconos = {}; const faltan = []
for (const [c, bases] of CONCEPTOS) {
  if (iconos[c]) continue
  const e = {}
  for (const fam of Object.keys(F)) { const r = buscar(fam, bases); if (r) e[fam] = r }
  // Se queda solo si está en Lucide (la familia base del CRM) y en al menos 3 familias más.
  if (e.lu && Object.keys(e).length >= 4) iconos[c] = e; else faltan.push(`${c} (${Object.keys(e).join(',') || 'ninguna'})`)
}
const variantes = Object.values(iconos).reduce((s, e) => s + Object.values(e).reduce((t, v) => t + (typeof v === 'string' ? 1 : Object.keys(v).length), 0), 0)
mkdirSync('laboratorio/src/plantillas/catalogos', { recursive: true })
writeFileSync('laboratorio/src/plantillas/catalogos/iconos.js', `/* Catálogo de íconos (D32). GENERADO por servidor/generar-iconos.mjs desde react-icons ${JSON.parse(readFileSync('node_modules/react-icons/package.json')).version}:
 * cada nombre existe de verdad. ${Object.keys(iconos).length} conceptos · ${Object.keys(FAMILIAS).length} familias · ${variantes} íconos en total (contando estilos).
 * No se edita a mano: se agrega el concepto en el generador y se vuelve a correr. */
export const FAMILIAS = ${JSON.stringify(FAMILIAS, null, 1)}

export const ICONOS = ${JSON.stringify(iconos)}
`)
console.log(`${Object.keys(iconos).length} conceptos, ${variantes} íconos con sus estilos. Descartados ${faltan.length}: ${faltan.join('; ')}`)
