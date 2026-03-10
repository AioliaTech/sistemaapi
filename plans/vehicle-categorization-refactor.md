# Refatoração: Categorização Centralizada de Veículos

## Problema Atual

### Situação:
- **21 parsers** diferentes chamam `definir_categoria_veiculo()`
- Função está em [`BaseParser`](../fetchers/base_parser.py:134) (classe base)
- Cada parser tem sua própria lógica de quando/como chamar
- Difícil de manter e melhorar em um único lugar
- Alguns parsers recebem categoria do XML, outros não
- Categoria pode vir vazia mesmo quando o XML tem o campo

### Problemas Identificados:

1. **Lógica duplicada**: Cada parser decide quando usar a função
2. **Inconsistência**: Alguns passam opcionais, outros não
3. **Difícil de testar**: Lógica espalhada em 21 arquivos
4. **Difícil de melhorar**: Mudanças precisam ser testadas em todos os parsers

## Solução Proposta

### Arquitetura Nova:

```
┌─────────────────────────────────────────────────────────────┐
│                    VehicleCategorizer                        │
│                  (Classe Independente)                       │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  categorize(vehicle_data: Dict) -> str             │    │
│  │                                                     │    │
│  │  Hierarquia de Decisão:                            │    │
│  │  1. Categoria do XML (se confiável)                │    │
│  │  2. Palavra-chave no título/modelo                 │    │
│  │  3. Mapeamento por modelo                          │    │
│  │  4. Número de portas (5=hatch, 4=sedan)            │    │
│  │  5. Opcionais (limpador traseiro)                  │    │
│  │  6. Código FIPE (futuro)                           │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  _detect_from_xml_category()                       │    │
│  │  _detect_from_keywords()                           │    │
│  │  _detect_from_mapping()                            │    │
│  │  _detect_from_doors()                              │    │
│  │  _detect_from_optionals()                          │    │
│  │  _detect_from_fipe()  # Futuro                     │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │
                            │ usa
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                      BaseParser                              │
│                                                              │
│  normalize_vehicle(vehicle: Dict) -> Dict                   │
│    ├─ Normaliza campos básicos                              │
│    ├─ Chama VehicleCategorizer.categorize()                 │
│    └─ Retorna veículo com categoria definida                │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │
                            │ herdam
                            │
┌───────────────────────────┴─────────────────────────────────┐
│  BoomParser  │  RevendamaisParser  │  AltimusParser  │ ...  │
│                                                              │
│  Apenas fazem parse do XML/JSON                             │
│  Não se preocupam com categorização                         │
└─────────────────────────────────────────────────────────────┘
```

## Estrutura de Arquivos

```
fetchers/
├── __init__.py
├── base_parser.py              # Classe base (simplificada)
├── vehicle_categorizer.py      # NOVA: Lógica de categorização
├── boom_parser.py
├── revendamais_parser.py
└── ...

vehicle_mappings.py             # Mantém os mapeamentos
```

## Implementação Detalhada

### 1. Nova Classe: `VehicleCategorizer`

```python
# fetchers/vehicle_categorizer.py

from typing import Dict, Optional, List, Tuple
from vehicle_mappings import MAPEAMENTO_CATEGORIAS, OPCIONAL_CHAVE_HATCH
from unidecode import unidecode
import re

class VehicleCategorizer:
    """
    Classe centralizada para categorização de veículos.
    Usa múltiplos critérios em ordem de prioridade.
    """
    
    def __init__(self):
        self.mapeamento = MAPEAMENTO_CATEGORIAS
        self.opcional_hatch = OPCIONAL_CHAVE_HATCH
    
    def categorize(self, vehicle_data: Dict) -> str:
        """
        Categoriza um veículo usando hierarquia de critérios.
        
        Args:
            vehicle_data: Dicionário com dados do veículo:
                - categoria: str (do XML, pode estar vazio)
                - modelo: str
                - titulo: str
                - versao: str
                - portas: int
                - opcionais: str
                - tipo: str (carro/moto)
        
        Returns:
            Categoria do veículo (Hatch, Sedan, SUV, etc.)
        """
        # 1. Categoria do XML (se confiável)
        categoria = self._detect_from_xml_category(vehicle_data)
        if categoria:
            return categoria
        
        # 2. Palavra-chave no título/modelo (HATCH, SEDAN, etc.)
        categoria = self._detect_from_keywords(vehicle_data)
        if categoria:
            return categoria
        
        # 3. Mapeamento por modelo (mais específico)
        categoria = self._detect_from_mapping(vehicle_data)
        if categoria:
            # Se for ambíguo (hatch,sedan), usa critérios adicionais
            if categoria == "hatch,sedan":
                return self._resolve_ambiguous(vehicle_data)
            return categoria
        
        # 4. Fallback: retorna None (será tratado pelo parser)
        return None
    
    def _detect_from_xml_category(self, vehicle_data: Dict) -> Optional[str]:
        """
        Usa categoria do XML se for confiável.
        
        Categorias confiáveis:
        - SUV, Caminhonete, Furgão, Coupe, Conversível, etc.
        
        Categorias NÃO confiáveis (podem estar erradas):
        - Hatch, Sedan (muitos XMLs erram)
        """
        categoria_xml = vehicle_data.get("categoria", "").strip()
        if not categoria_xml:
            return None
        
        # Normaliza
        categoria_norm = self._normalize_text(categoria_xml)
        
        # Lista de categorias confiáveis (não ambíguas)
        categorias_confiaveis = [
            "suv", "caminhonete", "furgao", "coupe", "conversivel",
            "station wagon", "minivan", "off-road", "utilitario"
        ]
        
        for cat in categorias_confiaveis:
            if cat in categoria_norm:
                return categoria_xml.title()  # Retorna com capitalização
        
        # Hatch/Sedan do XML não são confiáveis, ignora
        return None
    
    def _detect_from_keywords(self, vehicle_data: Dict) -> Optional[str]:
        """
        Detecta categoria por palavras-chave em TODOS os campos de texto.
        Varre: título, modelo, versão, observação, opcionais, etc.
        """
        # Concatena TODOS os campos de texto disponíveis
        campos_texto = [
            vehicle_data.get('titulo', ''),
            vehicle_data.get('modelo', ''),
            vehicle_data.get('versao', ''),
            vehicle_data.get('observacao', ''),
            vehicle_data.get('opcionais', ''),
            vehicle_data.get('categoria', ''),  # Categoria do XML também
        ]
        
        # Junta tudo em um único texto para busca
        texto_completo = ' '.join(campos_texto).upper()
        
        # Busca por palavras-chave (ordem de especificidade)
        # Mais específicas primeiro para evitar falsos positivos
        
        # Categorias específicas
        if "STATION WAGON" in texto_completo or "SW" in texto_completo:
            return "Station Wagon"
        if "PICK-UP" in texto_completo or "PICKUP" in texto_completo:
            return "Caminhonete"
        if "CONVERSIVEL" in texto_completo or "CABRIOLET" in texto_completo or "CABRIO" in texto_completo:
            return "Conversível"
        if "COUPE" in texto_completo or "COUPÉ" in texto_completo:
            return "Coupe"
        if "MINIVAN" in texto_completo or "VAN" in texto_completo:
            return "Minivan"
        if "FURGAO" in texto_completo or "FURGÃO" in texto_completo:
            return "Furgão"
        if "OFF-ROAD" in texto_completo or "OFFROAD" in texto_completo:
            return "Off-road"
        if "UTILITARIO" in texto_completo or "UTILITÁRIO" in texto_completo:
            return "Utilitário"
        
        # SUV (várias variações)
        if any(palavra in texto_completo for palavra in ["SUV", "SPORT UTILITY", "CROSSOVER"]):
            return "SUV"
        
        # Hatch e Sedan (mais genéricas, por último)
        if "HATCHBACK" in texto_completo or "HATCH" in texto_completo:
            return "Hatch"
        if "SEDAN" in texto_completo:
            return "Sedan"
        
        return None
    
    def _detect_from_mapping(self, vehicle_data: Dict) -> Optional[str]:
        """
        Usa mapeamento de modelos com sistema de scoring.
        """
        modelo = vehicle_data.get("modelo", "")
        if not modelo:
            return None
        
        modelo_norm = self._normalize_text(modelo)
        
        # Busca no mapeamento pelo MELHOR match
        matches = []
        
        for modelo_mapeado, categoria_result in self.mapeamento.items():
            modelo_mapeado_norm = self._normalize_text(modelo_mapeado)
            
            if modelo_mapeado_norm in modelo_norm:
                # Score: número de palavras + comprimento
                palavras_mapeado = modelo_mapeado_norm.split()
                palavras_modelo = modelo_norm.split()
                palavras_match = sum(1 for p in palavras_mapeado if p in palavras_modelo)
                score = (palavras_match * 100) + len(modelo_mapeado_norm)
                
                matches.append({
                    'categoria': categoria_result,
                    'score': score
                })
        
        if matches:
            matches.sort(key=lambda x: x['score'], reverse=True)
            return matches[0]['categoria']
        
        return None
    
    def _resolve_ambiguous(self, vehicle_data: Dict) -> str:
        """
        Resolve categorias ambíguas (hatch,sedan) usando múltiplos critérios.
        
        Critérios em ordem:
        1. Número de portas (5=hatch, 4=sedan)
        2. Opcionais (limpador traseiro = hatch)
        3. Palavra "Sport" no nome (geralmente hatch)
        4. Default: Sedan
        """
        # 1. Número de portas
        portas = vehicle_data.get("portas")
        if portas:
            try:
                portas_int = int(portas)
                if portas_int == 5:
                    return "Hatch"
                elif portas_int == 4:
                    return "Sedan"
            except (ValueError, TypeError):
                pass
        
        # 2. Opcionais (limpador traseiro)
        opcionais = vehicle_data.get("opcionais", "")
        if opcionais:
            opcionais_norm = self._normalize_text(opcionais)
            opcional_chave_norm = self._normalize_text(self.opcional_hatch)
            if opcional_chave_norm in opcionais_norm:
                return "Hatch"
        
        # 3. Palavra "Sport" no modelo/título
        texto = f"{vehicle_data.get('modelo', '')} {vehicle_data.get('titulo', '')}".upper()
        if "SPORT" in texto:
            return "Hatch"
        
        # 4. Default: Sedan (mais comum quando não há informação)
        return "Sedan"
    
    def _normalize_text(self, texto: str) -> str:
        """Normaliza texto para comparação."""
        if not texto:
            return ""
        texto_norm = unidecode(str(texto)).lower()
        texto_norm = re.sub(r'[-_./]', ' ', texto_norm)
        texto_norm = re.sub(r'[^a-z0-9\s]', '', texto_norm)
        texto_norm = re.sub(r'\s+', ' ', texto_norm).strip()
        return texto_norm
```

### 2. Modificar `BaseParser`

```python
# fetchers/base_parser.py

from .vehicle_categorizer import VehicleCategorizer

class BaseParser(ABC):
    def __init__(self):
        self.categorizer = VehicleCategorizer()
    
    def normalize_vehicle(self, vehicle: Dict) -> Dict:
        """Normaliza um veículo para o formato padrão"""
        # Aplica normalização nas fotos
        fotos = vehicle.get("fotos", [])
        vehicle["fotos"] = self.normalize_fotos(fotos)
        
        # NOVA LÓGICA: Categoriza automaticamente se não tiver categoria
        if not vehicle.get("categoria"):
            vehicle["categoria"] = self.categorizer.categorize(vehicle)
        
        return {
            "id": vehicle.get("id"),
            "tipo": vehicle.get("tipo"),
            "titulo": vehicle.get("titulo"),
            # ... resto dos campos
        }
```

### 3. Simplificar Parsers

Agora os parsers não precisam se preocupar com categorização:

```python
# fetchers/boom_parser.py (SIMPLIFICADO)

class BoomParser(BaseParser):
    def parse(self, data: Any, url: str) -> List[Dict]:
        # ... código de parsing ...
        
        parsed = self.normalize_vehicle({
            "id": v.get('id'),
            "tipo": tipo_final,
            "titulo": v.get('titulo'),
            "modelo": v.get('modelo'),
            "portas": v.get('portas'),
            "opcionais": opcionais_str,
            "categoria": None,  # Será preenchido automaticamente
            # ... resto dos campos
        })
```

## Exemplo Prático: Varredura Completa

### Caso Real:
```xml
<veiculo>
  <modelo>Polo</modelo>
  <titulo>Polo 1.0 Flex 12V 5p</titulo>
  <versao></versao>
  <observacao>
    Polo Sedan 1.0 Flex 2017/2018, Bancos em tecido, 
    Rodas de Liga Leve, Som Original, Ar-Condicionado...
  </observacao>
  <categoria></categoria>
</veiculo>
```

### Detecção:
1. **Modelo**: "Polo" → Ambíguo (pode ser hatch ou sedan)
2. **Título**: "Polo 1.0 Flex 12V 5p" → Sem palavra-chave
3. **Observação**: "Polo **Sedan** 1.0 Flex..." → **ENCONTROU "SEDAN"!**
4. **Resultado**: **Sedan** ✅

Sem a varredura completa, seria classificado incorretamente como Hatch (por ter 5 portas).

## Vantagens da Nova Arquitetura

### 1. **Centralização**
- ✅ Toda lógica de categorização em um único arquivo
- ✅ Fácil de manter e melhorar
- ✅ Mudanças afetam todos os parsers automaticamente

### 2. **Varredura Completa de Texto**
- ✅ Busca palavras-chave em TODOS os campos de texto
- ✅ Não depende apenas de título/modelo
- ✅ Encontra categoria em observação, opcionais, versão, etc.
- ✅ Exemplo: "Polo Sedan 1.6" na observação → detecta "Sedan"

### 3. **Testabilidade**
- ✅ Pode testar `VehicleCategorizer` isoladamente
- ✅ Testes unitários para cada critério
- ✅ Fácil adicionar novos casos de teste

### 3. **Extensibilidade**
- ✅ Fácil adicionar novos critérios (ex: código FIPE)
- ✅ Fácil ajustar prioridades
- ✅ Fácil adicionar lógica específica por marca

### 4. **Robustez**
- ✅ Múltiplos critérios de fallback
- ✅ Resolve ambiguidades de forma consistente
- ✅ Menos erros de categorização

### 5. **Simplicidade nos Parsers**
- ✅ Parsers focam apenas em extrair dados
- ✅ Não precisam se preocupar com categorização
- ✅ Código mais limpo e legível

## Funcionalidade Adicional: Monitoramento de Categorização

### Dashboard: Coluna de Veículos Sem Categoria

Adicionar uma nova coluna no dashboard que mostra quantos veículos estão sem categoria mapeada.

#### Modificações Necessárias:

**1. Backend: Calcular estatísticas de categorização**

```python
# client_manager.py

def get_categorization_stats(self, slug: str) -> Dict:
    """
    Retorna estatísticas de categorização para um cliente.
    
    Returns:
        {
            "total": 100,
            "sem_categoria": 5,
            "percentual_sem_categoria": 5.0
        }
    """
    data_file = self.get_client_data_file(slug)
    if not data_file.exists():
        return {"total": 0, "sem_categoria": 0, "percentual_sem_categoria": 0}
    
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        veiculos = data.get("veiculos", [])
        total = len(veiculos)
        
        if total == 0:
            return {"total": 0, "sem_categoria": 0, "percentual_sem_categoria": 0}
        
        # Conta veículos sem categoria ou com categoria None/vazia
        sem_categoria = sum(
            1 for v in veiculos 
            if not v.get("categoria") or v.get("categoria") in [None, "", "Não informado"]
        )
        
        percentual = (sem_categoria / total) * 100 if total > 0 else 0
        
        return {
            "total": total,
            "sem_categoria": sem_categoria,
            "percentual_sem_categoria": round(percentual, 1)
        }
    except Exception as e:
        print(f"[ERRO] Erro ao calcular stats de categorização: {e}")
        return {"total": 0, "sem_categoria": 0, "percentual_sem_categoria": 0}
```

**2. Backend: Adicionar stats ao endpoint do dashboard**

```python
# main.py

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: dict = Depends(require_auth)):
    clients = client_manager.list_clients()
    
    # Adiciona estatísticas de categorização para cada cliente
    clients_with_stats = []
    for client in clients:
        client_dict = client.to_dict()
        
        # Adiciona stats de categorização
        cat_stats = client_manager.get_categorization_stats(client.slug)
        client_dict["categorization_stats"] = cat_stats
        
        clients_with_stats.append(client_dict)
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "clients": clients_with_stats,
            "base_url": BASE_URL
        }
    )
```

**3. Frontend: Adicionar coluna na tabela**

```html
<!-- templates/dashboard.html -->

<thead>
  <tr>
    <th>Nome / Slug</th>
    <th>Parser</th>
    <th>Status</th>
    <th>Veículos</th>                    <!-- NOVA COLUNA -->
    <th>Sem Categoria</th>                <!-- NOVA COLUNA -->
    <th>Última Atualização</th>
    <th class="base-url-cell">URL Base</th>
    <th style="text-align:right">Ações</th>
  </tr>
</thead>

<tbody>
  {% for client in clients %}
  <tr>
    <!-- ... outras colunas ... -->
    
    <!-- Coluna de Total de Veículos -->
    <td>
      <span class="vehicle-count">
        {{ client.vehicle_count or 0 }}
      </span>
    </td>
    
    <!-- Coluna de Veículos Sem Categoria -->
    <td>
      {% set stats = client.categorization_stats %}
      {% if stats.sem_categoria > 0 %}
        <span class="uncategorized-badge warning" 
              title="{{ stats.percentual_sem_categoria }}% sem categoria">
          {{ stats.sem_categoria }}
          <span class="percentage">({{ stats.percentual_sem_categoria }}%)</span>
        </span>
      {% else %}
        <span class="uncategorized-badge success">✓ 0</span>
      {% endif %}
    </td>
    
    <!-- ... outras colunas ... -->
  </tr>
  {% endfor %}
</tbody>
```

**4. Frontend: Estilos CSS**

```css
/* static/style.css */

.vehicle-count {
  font-weight: 600;
  color: var(--text-primary);
}

.uncategorized-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.uncategorized-badge.success {
  background-color: #d4edda;
  color: #155724;
}

.uncategorized-badge.warning {
  background-color: #fff3cd;
  color: #856404;
}

.uncategorized-badge .percentage {
  font-size: 11px;
  opacity: 0.8;
}
```

#### Visualização no Dashboard:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Nome / Slug  │ Parser  │ Status  │ Veículos │ Sem Categoria │ Última... │
├─────────────────────────────────────────────────────────────────────────┤
│ Cliente A    │ Boom    │ Rodando │   150    │  ✓ 0          │ 2h atrás  │
│ cliente-a    │         │         │          │               │           │
├─────────────────────────────────────────────────────────────────────────┤
│ Cliente B    │ Revenda │ Rodando │    85    │  5 (5.9%)     │ 1h atrás  │
│ cliente-b    │ mais    │         │          │  ⚠️           │           │
├─────────────────────────────────────────────────────────────────────────┤
│ Cliente C    │ Altimus │ Rodando │   200    │  12 (6.0%)    │ 30m atrás │
│ cliente-c    │         │         │          │  ⚠️           │           │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Benefícios:

- ✅ **Visibilidade**: Identifica rapidamente clientes com problemas de categorização
- ✅ **Monitoramento**: Acompanha a qualidade dos dados
- ✅ **Priorização**: Sabe quais clientes precisam de atenção
- ✅ **Métricas**: Percentual ajuda a entender a gravidade

#### Melhorias Futuras:

**1. Filtro por Categoria**
- Adicionar filtro para mostrar apenas clientes com veículos sem categoria
- Ordenar por número/percentual de veículos sem categoria

**2. Detalhamento**
- Clicar no badge abre modal com lista de veículos sem categoria
- Permite editar categoria manualmente

**3. Alertas**
- Notificação quando percentual de veículos sem categoria > 10%
- Email semanal com resumo de categorização

**4. Histórico**
- Gráfico mostrando evolução da categorização ao longo do tempo
- Comparação antes/depois da refatoração

## Melhorias Futuras

### 1. **Integração com API FIPE**
```python
def _detect_from_fipe(self, vehicle_data: Dict) -> Optional[str]:
    """Usa código FIPE para determinar categoria."""
    codigo_fipe = vehicle_data.get("codigo_fipe")
    if codigo_fipe:
        # Consulta API FIPE ou banco local
        return self._query_fipe_category(codigo_fipe)
    return None
```

### 2. **Machine Learning (Futuro)**
```python
def _detect_from_ml(self, vehicle_data: Dict) -> Optional[str]:
    """Usa modelo ML treinado para categorizar."""
    features = self._extract_features(vehicle_data)
    return self.ml_model.predict(features)
```

### 3. **Cache de Categorização**
```python
def categorize(self, vehicle_data: Dict) -> str:
    # Cache por modelo+ano
    cache_key = f"{vehicle_data.get('modelo')}_{vehicle_data.get('ano')}"
    if cache_key in self.cache:
        return self.cache[cache_key]
    
    categoria = self._categorize_internal(vehicle_data)
    self.cache[cache_key] = categoria
    return categoria
```

## Plano de Implementação

### Fase 1: Criar Nova Estrutura
- [ ] Criar `fetchers/vehicle_categorizer.py`
- [ ] Implementar classe `VehicleCategorizer`
- [ ] Adicionar testes unitários

### Fase 2: Integrar com BaseParser
- [ ] Modificar `BaseParser.normalize_vehicle()`
- [ ] Remover `definir_categoria_veiculo()` do BaseParser
- [ ] Testar com um parser (BoomParser)

### Fase 3: Migrar Parsers
- [ ] Simplificar todos os 21 parsers
- [ ] Remover lógica de categorização duplicada
- [ ] Testar cada parser individualmente

### Fase 4: Validação
- [ ] Testar com dados reais de todos os clientes
- [ ] Comparar categorias antes/depois
- [ ] Ajustar critérios se necessário

### Fase 5: Melhorias
- [ ] Adicionar detecção por código FIPE
- [ ] Adicionar mais critérios de ambiguidade
- [ ] Otimizar performance com cache

## Riscos e Mitigações

### Risco 1: Mudança de Comportamento
**Mitigação**: 
- Testar extensivamente antes de deploy
- Comparar categorias antigas vs novas
- Fazer rollback fácil se necessário

### Risco 2: Performance
**Mitigação**:
- Adicionar cache de categorização
- Otimizar normalização de texto
- Medir performance antes/depois

### Risco 3: Casos Edge
**Mitigação**:
- Documentar todos os casos especiais
- Adicionar testes para cada caso
- Permitir override manual se necessário

## Conclusão

Esta refatoração traz:
- ✅ **Manutenibilidade**: Código centralizado e organizado
- ✅ **Qualidade**: Menos erros de categorização
- ✅ **Extensibilidade**: Fácil adicionar novos critérios
- ✅ **Testabilidade**: Testes isolados e completos

A implementação pode ser feita de forma incremental, minimizando riscos.
