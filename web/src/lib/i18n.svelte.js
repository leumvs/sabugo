/** Metric names are absent on purpose: they are the column names the other
 *  tools use, and translating them would break reading a Sabugo sheet beside
 *  one of theirs. */

const dictionaries = {
  pt: {
    parameters: "Opções de análise",
    preprocessing: "Pré-processamento da imagem",
    features: "Extração de features",

    analysisMode: "Modo de análise",
    modeBroken: "Raízes quebradas",
    modeWhole: "Raiz inteira",
    calibration: "Converter pixels para unidades físicas",
    thresholdMethod: "Método de limiar",
    thresholdManual: "Manual",
    thresholdOtsu: "Auto — otsu",
    thresholdLevel: "Nível de limiar da imagem",
    invertImage: "Inverter as cores da imagem",
    keepLargest: "Manter só o maior componente",
    filterNonRoot: "Filtrar objetos que não são raiz",
    fillHoles: "Preencher buracos nas raízes",
    maximumSize: "Tamanho máximo (mm²)",
    edgeSmoothing: "Suavizar a borda",
    edgeSmoothingThreshold: "Limiar de suavização",
    rootPruning: "Podar o esqueleto",
    rootPruningThreshold: "Limiar de poda",
    diameterRanges: "Faixas de diâmetro da raiz (em mm)",
    showMedialAxis: "Mostrar o eixo medial",
    medialAxisWidth: "Espessura do eixo medial",
    colourByDiameter: "Colorir o eixo medial pela faixa de diâmetro",
    showRootContour: "Mostrar o contorno da raiz",
    contourWidth: "Espessura do contorno",
    showConvexHull: "Mostrar o casco convexo",
    showHoles: "Mostrar os buracos",
    showDistanceMap: "Mostrar o mapa de distância",

    load: "abrindo a imagem",
    segment: "segmentando",
    skeletonize: "esqueletonizando",
    prune: "podando",
    topology: "lendo a topologia",
    aggregate: "agregando",
    render: "desenhando",
    stage: "amostra",
    language: "Idioma",
    darkMode: "Modo escuro",
    log: "registro",
    byClass: "por classe de diâmetro",
    downloadCsv: "Baixar CSV",
    drawHint: "Arraste sobre a imagem para marcar uma região.",
    roiReplacesWhole: "uma linha por região, sem a imagem inteira",
    removeRegion: "Remover",

    dropHere: "Solte um scan aqui",
    dropHint:
      "Diga o DPI da digitalização. Toda medida sai em milímetros, e é o DPI que converte pixel em milímetro.",
    noResultYet: "Nenhuma medida ainda.",
    leaveWarning: "Você tem uma medida que não baixou. Sair perde os números.",

    dpiHint: "Resolução da digitalização. Sem ela nada sai em milímetros.",
    dpiUnusual: "Fora da faixa usual de scanner (200–1200). Vai medir assim mesmo.",
    thresholdHint: "Raiz escura sobre fundo claro: o pixel entra quando é mais escuro que isto.",
    pruningHint: "Folga em pixels somada ao raio da bifurcação, não comprimento absoluto.",
    classCount: "{n} classes de diâmetro",

    diameter_ranges_not_numbers: "só números, separados por vírgula",
    diameter_ranges_too_many: "no máximo 11 limites",
    diameter_ranges_must_be_positive: "todos maiores que zero",
    diameter_ranges_must_be_strictly_increasing: "em ordem crescente",

    menuFile: "Arquivo",
    menuEdit: "Editar",
    menuView: "Ver",
    menuHelp: "Ajuda",
    openImage: "Abrir imagem",
    save: "Salvar",
    saveDisplayed: "Imagem exibida",
    saveAnnotation: "Anotação",
    saveFeatures: "Features",
    saveSettings: "Configurações",
    loadAnnotation: "Carregar anotação",
    loadSettings: "Carregar configurações",
    clearRois: "Limpar todos os ROIs",
    invertColors: "Inverter cores",
    about: "Sobre",
    aboutText:
      "Sabugo mede raiz e fibra por imagem no navegador. Nada do que você mede fica salvo no servidor.",
    close: "Fechar",

    displayOutput: "Saída exibida",
    inputImage: "Imagem de entrada",
    segmentedImage: "Imagem segmentada",
    processedImage: "Imagem processada",
    rotation: "Rotação horária",
    zoomOut: "Menos zoom",
    zoomIn: "Mais zoom",
    zoomFit: "Ajustar à tela",
    panMode: "Modo de arrasto",
    roiMode: "Modo região de interesse",
    run: "Analisar",
    previewSegmented: "Prever imagem segmentada",
    outputDisplay: "Exibição de saída",
    wholeRootOnly: "As duas só valem em raiz inteira.",

    roiManager: "Gerenciador de ROI",
    roiName: "Nome",
    roiClass: "Classe",
    roiList: "Lista de ROIs",
    addRoi: "Adicionar",
    roiLimit: "Máximo de 10 regiões por análise.",

    featuresTab: "Features",
    noRows: "Nenhuma linha ainda. Analise uma imagem.",
    rowsKeep: "acumula; só limpa ao trocar o modo de análise",

    rangeRow: "Faixa",
    rangeTo: "até",
    rangeAbove: "acima.",
    addRange: "Adicionar faixa",
    removeRange: "Remover faixa",

    colourStats: "Estatísticas de cor",
    wholeImage: "Imagem inteira",
    mean: "Média",
    sd: "Desvio-padrão",
    needImage: "Abra uma imagem primeiro.",

    annotation_needs_six_columns: "A anotação precisa de seis colunas por linha.",
    annotation_needs_numbers: "A anotação tem coordenadas que não são números.",
    annotation_is_empty: "A anotação não tem nenhuma região.",
    settings_unreadable: "O arquivo de configurações não abriu.",

    pending: "na fila",
    processing: "medindo",
    completed: "pronto",
    failed: "falhou",

    INVALID_PARAMS: "Um parâmetro está fora da faixa aceita.",
    INVALID_IMAGE: "O arquivo não abriu como imagem.",
    NOT_FOUND: "Esta análise não existe mais.",
    UNSUPPORTED_FORMAT: "Formato não aceito. Use BMP, JPEG, PNG ou TIFF de página única.",
    IMAGE_TOO_LARGE:
      "Imagem acima de 100 megapixels. Escaneie em DPI menor — reduzir aqui mudaria a medida sem você saber.",
    NO_ROOTS_DETECTED:
      'Nenhuma raiz na imagem. Ajuste o limiar, ou marque "Inverter as cores da imagem" se a raiz for clara sobre fundo escuro.',
    RATE_LIMITED:
      "Você passou do limite de análises por hora deste endereço. Tente de novo mais tarde.",
    SERVICE_AT_CAPACITY:
      "A fila está cheia. É uma imagem por vez; tente de novo em alguns minutos.",
    PROCESSING_TIMEOUT: "O processamento passou de 120 segundos e foi interrompido.",
    INTERNAL_ERROR: "Algo falhou no servidor.",
  },

  en: {
    parameters: "Analysis options",
    preprocessing: "Image pre-processing",
    features: "Feature extraction",

    analysisMode: "Analysis mode",
    modeBroken: "Broken roots",
    modeWhole: "Whole root",
    calibration: "Convert pixels to physical units",
    thresholdMethod: "Thresholding method",
    thresholdManual: "Manual",
    thresholdOtsu: "Auto — otsu",
    thresholdLevel: "Image thresholding level",
    invertImage: "Invert image colors",
    keepLargest: "Keep largest component",
    filterNonRoot: "Filter non-root objects",
    fillHoles: "Fill holes in root objects",
    maximumSize: "Maximum size (mm²)",
    edgeSmoothing: "Enable edge smoothing",
    edgeSmoothingThreshold: "Edge smoothing threshold",
    rootPruning: "Enable root pruning",
    rootPruningThreshold: "Root pruning threshold",
    diameterRanges: "Root diameter ranges (in mm)",
    showMedialAxis: "Show medial axis",
    medialAxisWidth: "Medial axis width",
    colourByDiameter: "Color medial axis based on diameter range",
    showRootContour: "Show root contour",
    contourWidth: "Contour width",
    showConvexHull: "Show convex hull",
    showHoles: "Show holes",
    showDistanceMap: "Show distance map",

    load: "opening the image",
    segment: "segmenting",
    skeletonize: "skeletonizing",
    prune: "pruning",
    topology: "reading the topology",
    aggregate: "aggregating",
    render: "drawing",
    stage: "sample",
    language: "Language",
    darkMode: "Dark mode",
    log: "log",
    byClass: "by diameter class",
    downloadCsv: "Download CSV",
    drawHint: "Drag on the image to mark a region.",
    roiReplacesWhole: "one row per region, no whole image",
    removeRegion: "Remove",

    dropHere: "Drop a scan here",
    dropHint:
      "Tell us the scanning resolution. Every measurement is in millimetres, and DPI is what turns pixels into them.",
    noResultYet: "No measurement yet.",
    leaveWarning: "You have a measurement you have not downloaded. Leaving loses the numbers.",

    dpiHint: "Resolution of the scan. Without it nothing comes out in millimetres.",
    dpiUnusual: "Outside the usual scanner range (200–1200). It will measure anyway.",
    thresholdHint: "Dark root on a light background: a pixel counts when it is darker than this.",
    pruningHint: "Slack in pixels added to the radius at the branch point, not an absolute length.",
    classCount: "{n} diameter classes",

    diameter_ranges_not_numbers: "numbers only, separated by commas",
    diameter_ranges_too_many: "at most 11 boundaries",
    diameter_ranges_must_be_positive: "all greater than zero",
    diameter_ranges_must_be_strictly_increasing: "in increasing order",

    menuFile: "File",
    menuEdit: "Edit",
    menuView: "View",
    menuHelp: "Help",
    openImage: "Open image",
    save: "Save",
    saveDisplayed: "Displayed image",
    saveAnnotation: "Annotation",
    saveFeatures: "Features",
    saveSettings: "Settings",
    loadAnnotation: "Load annotation",
    loadSettings: "Load settings",
    clearRois: "Clear all ROIs",
    invertColors: "Invert colors",
    about: "About",
    aboutText:
      "Sabugo measures roots and fibres from images in the browser. Nothing you measure is kept on the server.",
    close: "Close",

    displayOutput: "Display output",
    inputImage: "Input image",
    segmentedImage: "Segmented image",
    processedImage: "Processed image",
    rotation: "Image clockwise rotation",
    zoomOut: "Zoom out",
    zoomIn: "Zoom in",
    zoomFit: "Zoom to fit",
    panMode: "Image panning mode",
    roiMode: "Region of interest mode",
    run: "Run analysis",
    previewSegmented: "Preview segmented image",
    outputDisplay: "Output display",
    wholeRootOnly: "Both apply to whole root only.",

    roiManager: "ROI Manager",
    roiName: "Name",
    roiClass: "Class",
    roiList: "ROI list",
    addRoi: "Add",
    roiLimit: "At most 10 regions per analysis.",

    featuresTab: "Features",
    noRows: "No rows yet. Analyse an image.",
    rowsKeep: "accumulates; only a change of analysis mode clears it",

    rangeRow: "Range",
    rangeTo: "to",
    rangeAbove: "above.",
    addRange: "Add range",
    removeRange: "Remove range",

    colourStats: "Color statistics",
    wholeImage: "Whole image",
    mean: "Mean",
    sd: "Std. deviation",
    needImage: "Open an image first.",

    annotation_needs_six_columns: "The annotation needs six columns per line.",
    annotation_needs_numbers: "The annotation has coordinates that are not numbers.",
    annotation_is_empty: "The annotation has no region in it.",
    settings_unreadable: "The settings file did not open.",

    pending: "queued",
    processing: "measuring",
    completed: "done",
    failed: "failed",

    INVALID_PARAMS: "A parameter is outside the accepted range.",
    INVALID_IMAGE: "The file did not open as an image.",
    NOT_FOUND: "This analysis no longer exists.",
    UNSUPPORTED_FORMAT: "Format not accepted. Use BMP, JPEG, PNG or a single-page TIFF.",
    IMAGE_TOO_LARGE:
      "Image above 100 megapixels. Scan at a lower DPI — resizing here would change the measurement without telling you.",
    NO_ROOTS_DETECTED:
      'No root in the image. Adjust the threshold, or tick "Invert image colors" if the root is light on a dark background.',
    RATE_LIMITED: "You are over this address's hourly limit of analyses. Try again later.",
    SERVICE_AT_CAPACITY: "The queue is full. One image at a time; try again in a few minutes.",
    PROCESSING_TIMEOUT: "Processing went past 120 seconds and was stopped.",
    INTERNAL_ERROR: "Something failed on the server.",
  },
};

export const LANGUAGES = Object.keys(dictionaries);

function initial() {
  const stored = localStorage.getItem("sabugo.language");
  if (stored && stored in dictionaries) return stored;
  return navigator.language?.startsWith("pt") ? "pt" : "en";
}

// An object, not an exported `let`: a reassigned binding does not stay reactive
// across module boundaries in Svelte 5, a property of a $state proxy does.
export const locale = $state({ language: initial() });

export function setLanguage(next) {
  locale.language = next;
  localStorage.setItem("sabugo.language", next);
  document.documentElement.lang = next;
}

export function t(key) {
  return dictionaries[locale.language][key] ?? key;
}
