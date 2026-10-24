package sim

// Static mock material: clinical profiles, each with the story of events that
// worsens it, plus names and cities. Field values follow the dataset's own
// domains (backend/dataset/dicionario_dados.md), because the backend refuses
// anything outside them.
//
// Every profile is written so its jumps show in the queue: the calm ones enter
// with no clinical urgency (pain <= 3, mild limitation, no alarm word in the
// note), so they land near the bottom; the uncertain lesions (R91, D48) enter
// as class B; the cancers enter as A2. At the default pace an entry gets two
// events before the next one arrives, so the first two steps of every story
// carry the jump (a class change, hundreds of places); the third only shows
// when the events come faster than that.

// EventResults mirrors EVENT_RESULTS in backend/app/regulation/intake.py.
var EventResults = map[string][]string{
	"biopsia":              {"positivo", "negativo", "inconclusivo"},
	"hba1c":                {"resultado"},
	"pronto_socorro":       {"atendido_liberado", "observacao"},
	"internacao":           {"alta"},
	"exame_imagem":         {"estavel", "progressao"},
	"consulta_reavaliacao": {"piora", "estavel", "melhora"},
	"contato_telefonico": {
		"atendeu", "nao_atendeu", "relata_piora", "relata_melhora",
		"informou_cirurgia_outro_servico", "desistiu",
	},
	"falta": {"consulta", "exame", "avaliacao_pre_anestesica"},
}

// Procedures are the catalog ids the profiles use (backend/dataset/procedimentos.csv).
var Procedures = map[string]string{
	"PROC002": "Herniorrafia inguinal",
	"PROC004": "Colecistectomia videolaparoscopica",
	"PROC006": "Safenectomia / tratamento cirurgico de varizes",
	"PROC008": "Artroplastia total de joelho",
	"PROC011": "Mastectomia / setorectomia de mama",
	"PROC012": "Colectomia",
	"PROC014": "Tireoidectomia",
	"PROC017": "Ureterolitotripsia / nefrolitotripsia",
	"PROC020": "Lobectomia pulmonar",
}

// Step is one clinical event of a story. Value is valor_numerico (HbA1c %, days
// in hospital) and only goes out when set.
type Step struct {
	Kind        string
	Result      string
	Value       float64
	Description string
	Origin      string
}

// Profile is a kind of patient: what the request looks like when it enters,
// and the events that make it worse, in order.
type Profile struct {
	Label          string
	ProcedureID    string
	CID            string
	CIDDescription string
	Oncological    bool
	Sex            string // "" = any
	AgeMin, AgeMax int
	PainMin        int
	PainMax        int
	Limitations    []string
	Notes          []string
	Story          []Step
}

var Profiles = []Profile{
	{
		Label: "colelitíase", ProcedureID: "PROC004", CID: "K80.2",
		CIDDescription: "Calculose da vesicula biliar sem colecistite",
		AgeMin:         30, AgeMax: 75, PainMin: 1, PainMax: 3, Limitations: []string{"nenhuma", "leve"},
		Notes: []string{
			"Colelitiase sintomatica com colicas esporadicas. US com calculos de ate 1,5 cm. Solicito colecistectomia.",
			"Paciente com episodios de dor em hipocondrio direito apos refeicoes gordurosas. US com multiplos calculos.",
		},
		Story: []Step{
			{Kind: "pronto_socorro", Result: "observacao", Origin: "PS Hospital Sao Lucas",
				Description: "Colica biliar intensa com vomitos, US com vesicula de paredes espessadas. Observacao por 10 horas."},
			{Kind: "internacao", Result: "alta", Value: 4, Origin: "Hospital Sao Lucas",
				Description: "Internada por colecistite aguda, antibiotico endovenoso. Alta em 4 dias aguardando cirurgia."},
			{Kind: "consulta_reavaliacao", Result: "piora", Origin: "ambulatorio",
				Description: "Novos episodios de dor toda semana, intolerancia alimentar e perda de peso."},
		},
	},
	{
		Label: "hérnia inguinal", ProcedureID: "PROC002", CID: "K40.9",
		CIDDescription: "Hernia inguinal unilateral sem obstrucao ou gangrena",
		Sex:            "M", AgeMin: 25, AgeMax: 80, PainMin: 1, PainMax: 3, Limitations: []string{"nenhuma", "leve"},
		Notes: []string{
			"Hernia inguinal direita redutivel, desconforto aos esforcos. Solicito herniorrafia.",
			"Abaulamento inguinal esquerdo ha 1 ano, redutivel. Trabalha com carga.",
		},
		Story: []Step{
			{Kind: "pronto_socorro", Result: "atendido_liberado", Origin: "UPA Zona Norte",
				Description: "Dor e abaulamento inguinal apos esforco, hernia reduzida manualmente no PS."},
			{Kind: "pronto_socorro", Result: "observacao", Origin: "PS Hospital Sao Lucas",
				Description: "Hernia de dificil reducao com dor intensa, reduzida sob analgesia endovenosa. Observacao por 8 horas."},
			{Kind: "contato_telefonico", Result: "relata_piora", Origin: "call center",
				Description: "Paciente relata que a hernia sai varias vezes ao dia e nao consegue mais trabalhar."},
		},
	},
	{
		Label: "varizes", ProcedureID: "PROC006", CID: "I83.9",
		CIDDescription: "Varizes dos membros inferiores sem ulcera ou inflamacao",
		AgeMin:         35, AgeMax: 75, PainMin: 1, PainMax: 3, Limitations: []string{"nenhuma", "leve"},
		Notes: []string{
			"Varizes de grosso calibre em membro inferior esquerdo, edema vespertino. Solicito safenectomia.",
		},
		Story: []Step{
			{Kind: "pronto_socorro", Result: "observacao", Origin: "PS Hospital Sao Lucas",
				Description: "Tromboflebite superficial em safena magna, dor e calor local. Observacao e anticoagulacao."},
			{Kind: "internacao", Result: "alta", Value: 3, Origin: "Hospital Sao Lucas",
				Description: "Internacao por erisipela no membro com varizes. Antibiotico endovenoso, alta em 3 dias."},
			{Kind: "consulta_reavaliacao", Result: "piora", Origin: "ambulatorio",
				Description: "Edema progressivo e dermatite ocre em perna esquerda, dor ao fim do dia."},
		},
	},
	{
		Label: "cálculo renal", ProcedureID: "PROC017", CID: "N20.1",
		CIDDescription: "Calculo do ureter",
		AgeMin:         25, AgeMax: 70, PainMin: 2, PainMax: 3, Limitations: []string{"nenhuma", "leve"},
		Notes: []string{
			"Calculo ureteral distal de 7 mm, colicas esporadicas controladas com analgesia oral.",
		},
		Story: []Step{
			{Kind: "pronto_socorro", Result: "observacao", Origin: "PS Hospital Sao Lucas",
				Description: "Colica renal refrataria a analgesia oral, necessitou opioide. Observacao por 12 horas."},
			{Kind: "internacao", Result: "alta", Value: 2, Origin: "Hospital Sao Lucas",
				Description: "Pielonefrite obstrutiva, colocado cateter duplo J. Alta em 2 dias."},
			{Kind: "pronto_socorro", Result: "atendido_liberado", Origin: "UPA Zona Sul",
				Description: "Nova colica renal com hematuria, medicado e liberado."},
		},
	},
	{
		Label: "artrose de joelho", ProcedureID: "PROC008", CID: "M17.1",
		CIDDescription: "Outras gonartroses primarias",
		AgeMin:         55, AgeMax: 85, PainMin: 4, PainMax: 6, Limitations: []string{"moderada"},
		Notes: []string{
			"Gonartrose grau IV a direita, dor mecanica, falha de tratamento conservador. Solicito artroplastia.",
		},
		Story: []Step{
			{Kind: "pronto_socorro", Result: "atendido_liberado", Origin: "UPA Zona Norte",
				Description: "Queda por falseio do joelho direito, contusao sem fratura."},
			{Kind: "pronto_socorro", Result: "observacao", Origin: "PS Hospital Sao Lucas",
				Description: "Derrame articular volumoso e dor intensa, artrocentese no PS. Observacao por 6 horas."},
			{Kind: "consulta_reavaliacao", Result: "piora", Origin: "ambulatorio",
				Description: "Dor noturna, nao consegue caminhar uma quadra, passou a usar bengala."},
		},
	},
	{
		Label: "nódulo pulmonar suspeito", ProcedureID: "PROC020", CID: "R91",
		CIDDescription: "Achados anormais de exames para diagnostico por imagem do pulmao",
		AgeMin:         50, AgeMax: 80, PainMin: 0, PainMax: 2, Limitations: []string{"nenhuma", "leve"},
		Notes: []string{
			"Nodulo pulmonar solido de 14 mm em lobo superior direito, ex-tabagista. Solicito lobectomia.",
		},
		Story: []Step{
			{Kind: "exame_imagem", Result: "progressao", Origin: "radiologia",
				Description: "TC de torax: nodulo cresceu de 14 para 21 mm, contornos espiculados."},
			{Kind: "biopsia", Result: "positivo", Origin: "laboratorio de patologia",
				Description: "Biopsia transtoracica: adenocarcinoma pulmonar invasivo."},
			{Kind: "pronto_socorro", Result: "observacao", Origin: "PS Hospital Sao Lucas",
				Description: "Dispneia e dor toracica ventilatorio-dependente. Observacao por 12 horas."},
		},
	},
	{
		Label: "lesão de mama incerta", ProcedureID: "PROC011", CID: "D48.6",
		CIDDescription: "Neoplasia de comportamento incerto da mama",
		Sex:            "F", AgeMin: 35, AgeMax: 75, PainMin: 0, PainMax: 2, Limitations: []string{"nenhuma"},
		Notes: []string{
			"Nodulo de mama esquerda BI-RADS 4A, aguardando definicao. Solicito setorectomia.",
		},
		Story: []Step{
			{Kind: "biopsia", Result: "positivo", Origin: "laboratorio de patologia",
				Description: "Core biopsy: carcinoma ductal invasivo grau 2."},
			{Kind: "exame_imagem", Result: "progressao", Origin: "radiologia",
				Description: "RM de mamas: lesao aumentou de 2,1 para 3,4 cm, linfonodo axilar suspeito."},
			{Kind: "consulta_reavaliacao", Result: "piora", Origin: "ambulatorio",
				Description: "Retracao de pele sobre a lesao e dor local continua."},
		},
	},
	{
		Label: "câncer de cólon", ProcedureID: "PROC012", CID: "C18.7",
		CIDDescription: "Neoplasia maligna do colon sigmoide", Oncological: true,
		AgeMin: 45, AgeMax: 85, PainMin: 2, PainMax: 4, Limitations: []string{"leve", "moderada"},
		Notes: []string{
			"Adenocarcinoma de sigmoide confirmado por colonoscopia e AP. Estadiamento sem metastases. Solicito colectomia.",
		},
		Story: []Step{
			{Kind: "exame_imagem", Result: "progressao", Origin: "radiologia",
				Description: "TC de abdome: espessamento parietal maior e novos linfonodos mesentericos."},
			{Kind: "pronto_socorro", Result: "observacao", Origin: "PS Hospital Sao Lucas",
				Description: "Dor abdominal e distensao, parada de eliminacao de gases por 24 horas. Observacao."},
			{Kind: "internacao", Result: "alta", Value: 5, Origin: "Hospital Sao Lucas",
				Description: "Internado por quadro obstrutivo parcial, tratamento clinico. Alta em 5 dias."},
		},
	},
	{
		Label: "câncer de tireoide", ProcedureID: "PROC014", CID: "C73",
		CIDDescription: "Neoplasia maligna da glandula tireoide", Oncological: true,
		AgeMin: 25, AgeMax: 70, PainMin: 0, PainMax: 2, Limitations: []string{"nenhuma"},
		Notes: []string{
			"Carcinoma papilifero de tireoide em PAAF, nodulo de 2,3 cm. Solicito tireoidectomia total.",
		},
		Story: []Step{
			{Kind: "consulta_reavaliacao", Result: "piora", Origin: "ambulatorio",
				Description: "Rouquidao ha 3 semanas e sensacao de massa cervical."},
			{Kind: "exame_imagem", Result: "progressao", Origin: "radiologia",
				Description: "US cervical: nodulo de 2,3 para 3,1 cm e linfonodo cervical suspeito."},
			{Kind: "pronto_socorro", Result: "observacao", Origin: "PS Hospital Sao Lucas",
				Description: "Disfagia para solidos e dispneia aos esforcos. Observacao por 8 horas."},
		},
	},
}

// Extra worsening for a patient whose story is over: it still moves the index
// (until the events part caps) and keeps the events coming.
var Worsening = []Step{
	{Kind: "consulta_reavaliacao", Result: "piora", Origin: "ambulatorio",
		Description: "Reavaliacao: sintomas mais frequentes, uso de analgesia diaria."},
	{Kind: "contato_telefonico", Result: "relata_piora", Origin: "call center",
		Description: "Familiar relata piora da dor e que o paciente nao sai mais de casa."},
	{Kind: "pronto_socorro", Result: "atendido_liberado", Origin: "UPA Zona Sul",
		Description: "Atendido por dor relacionada a doenca de base, medicado e liberado."},
}

var FemaleNames = []string{
	"Ana", "Beatriz", "Carla", "Daniela", "Eliane", "Fernanda", "Gabriela", "Helena",
	"Ingrid", "Joana", "Larissa", "Marta", "Neusa", "Patricia", "Rosana", "Sandra", "Vera",
}

var MaleNames = []string{
	"Antonio", "Bruno", "Carlos", "Diego", "Eduardo", "Fabio", "Gilberto", "Henrique",
	"Igor", "Joao", "Luis", "Marcos", "Nelson", "Paulo", "Rafael", "Sergio", "Valter",
}

var Surnames = []string{
	"Almeida", "Brizola", "Cardoso", "Dutra", "Fagundes", "Goulart", "Heinz", "Lima",
	"Machado", "Nunes", "Oliveira", "Pereira", "Quadros", "Ramos", "Silveira", "Teixeira", "Vargas",
}

// City is where the patient lives and roughly how far it is from the hospital.
type City struct {
	Name string
	KM   int
}

var Cities = []City{
	{"Porto Alegre", 8}, {"Canoas", 18}, {"Alvorada", 20}, {"Viamao", 25}, {"Gravatai", 30},
	{"Sao Leopoldo", 35}, {"Novo Hamburgo", 45}, {"Guaiba", 30}, {"Santa Cruz do Sul", 155},
	{"Caxias do Sul", 125}, {"Pelotas", 260}, {"Santa Maria", 290}, {"Passo Fundo", 290},
}

var Comorbidities = []string{"nenhuma", "HAS", "DM2", "HAS; DM2", "obesidade", "HAS; dislipidemia", "DPOC"}

var ManualPriorities = []string{"alta", "media", "baixa"}
