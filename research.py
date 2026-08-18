"""
research.py - Mint-YT-Factory v5.0
Research-first scientific evidence layer.

Compatible with main.py and verify_claims.py.
No Gemini is used to create or summarize evidence.
"""
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import quote
import requests

CROSSREF_URL="https://api.crossref.org/v1/works"
SEMANTIC_SCHOLAR_URL="https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_PAPER_URL="https://api.semanticscholar.org/graph/v1/paper"
OPENALEX_URL="https://api.openalex.org/works"
TIMEOUT=30
MAX_CROSSREF_RESULTS=15
MAX_SEMANTIC_RESULTS=10
MAX_OPENALEX_RESULTS=12
MIN_ACCEPTED_SOURCES=2
MAX_EVIDENCE_SOURCES=5
MIN_ABSTRACT_CHARACTERS=120
MAX_EVIDENCE_TEXT_CHARACTERS=12000
SEMANTIC_RETRIES=2
SEMANTIC_BACKOFF_SECONDS=4
TITLE_SIMILARITY_MINIMUM=0.55
USER_AGENT="Mint-YT-Factory/5.0 (educational research verification)"
EVIDENCE_QUALITY_HIGH="high"
EVIDENCE_QUALITY_MODERATE="moderate"
EVIDENCE_QUALITY_NONE="none"

SESSION=requests.Session()
SESSION.headers.update({"User-Agent":USER_AGENT,"Accept":"application/json"})


def _get(url,params=None,retries=2,backoff=2):
    last=None
    for attempt in range(retries+1):
        try:
            r=SESSION.get(url,params=params,timeout=TIMEOUT)
            if r.status_code==429:
                ra=r.headers.get("Retry-After")
                try: delay=float(ra)
                except (TypeError,ValueError): delay=backoff*(attempt+1)
                if attempt<retries:
                    print(f"â ï¸ HTTP 429. Retrying in {delay:.1f}s..."); time.sleep(delay); continue
                raise RuntimeError("HTTP 429 rate limit exceeded.")
            if r.status_code>=500 and attempt<retries:
                delay=backoff*(attempt+1); print(f"â ï¸ HTTP {r.status_code}. Retrying in {delay:.1f}s..."); time.sleep(delay); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            last=e
            if attempt<retries:
                delay=backoff*(attempt+1); print(f"â ï¸ Request failed. Retrying in {delay:.1f}s..."); time.sleep(delay); continue
            raise last
    raise RuntimeError("HTTP request failed.")


def _clean(text):
    return re.sub(r"\s+"," ",str(text or "")).strip()


def _clean_abstract(text):
    text=_clean(text)
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",text)).strip()


def _normalize_doi(doi):
    doi=_clean(doi)
    doi=re.sub(r"^https?://doi\.org/|^https?://dx\.doi\.org/","",doi,flags=re.I)
    doi=re.sub(r"^doi:\s*","",doi,flags=re.I)
    return doi.strip().rstrip(".,;:)").lower()


def _generate_source_id(doi):
    doi=_normalize_doi(doi)
    if not doi: raise RuntimeError("Cannot generate source_id without a DOI.")
    return "doi_"+hashlib.sha256(doi.encode()).hexdigest()[:12]


def _normalize_title(title):
    return " ".join(re.sub(r"[^a-z0-9\s]"," ",_clean(title).lower()).split())


def _title_similarity(a,b):
    A=set(x for x in re.findall(r"[a-z0-9]+",_normalize_title(a)) if len(x)>=3)
    B=set(x for x in re.findall(r"[a-z0-9]+",_normalize_title(b)) if len(x)>=3)
    return len(A&B)/len(A|B) if A and B else 0.0

STOPWORDS={"how","do","does","did","can","could","would","should","the","a","an","and","or","to","of","in","on","for","with","from","why","what","is","are","be","their","they","them","these","those","this","that","about","into","through","will","your","our","its","it","as","by","at","over","under","than","then","when","where","which","who","during","using","long","way","ways","happen","happens","really"}
CONCEPT_GROUPS={
"bird":{"bird","birds","avian","passerine","songbird","songbirds","waterfowl","shorebird","shorebirds","raptor","raptors","pigeon","pigeons","swift","swifts"},
"navigation":{"navigate","navigates","navigated","navigating","navigation","navigational","orientation","orient","orients","oriented","compass","directional","direction","directions"},
"migration":{"migration","migrations","migratory","migrate","migrates","migrated","migrating","migrant","migrants"},
"flight":{"flight","flights","flying","fly","flies","flew","aerial","transoceanic"},
"magnetic":{"magnetic","magnetism","magnetoreception","geomagnetic","magneticfield"},
"brain":{"brain","brains","neural","neuronal","neuroscience","hippocampus","nidopallium","neuron","neurons"},
"climate":{"climate","climatic","warming","temperature","temperatures","environmental"},
"roots":{"root","roots","rooting","gravitropism","gravitropic","gravity"},
"plants":{"plant","plants","vegetation","seedling","seedlings"},
"pressure":{"pressure","pressures","depth","deep","deepsea"},
"ocean":{"ocean","oceans","marine","underwater","sea","seas"},
"space":{"space","planet","planets","star","stars","galaxy","galaxies","cosmic","astronomy","astronomical"},
"quantum":{"quantum","photons","photon","entanglement","superposition"},
"human":{"human","humans","people","person","persons"},
"medical":{"medical","medicine","clinical","patient","patients","health","disease","diseases","treatment"},
"technology":{"technology","technological","computer","computers","software","hardware","algorithm","algorithms","machine","machines"},
"memory":{"memory","memories","remember","remembering","recall","learning","learned"},
"sleep":{"sleep","sleeping","dream","dreaming","circadian","insomnia"},
"sound":{"sound","sounds","hearing","auditory","acoustic","frequency","frequencies"},
"light":{"light","visual","vision","photoreceptor","photoreceptors","wavelength","wavelengths"},
"gravity":{"gravity","gravitational","gravitation","weight"},
}

def _tokenize(text):
    return [x for x in re.findall(r"[a-z0-9]+",_clean(text).lower()) if x not in STOPWORDS and len(x)>=3]

def _concepts_from_text(text):
    t=set(_tokenize(text)); return {c for c,w in CONCEPT_GROUPS.items() if t&w}

def _stem_like_match(term,text):
    candidates={term}
    if term.endswith("ies") and len(term)>4: candidates.add(term[:-3]+"y")
    if term.endswith("ing") and len(term)>5: candidates.add(term[:-3])
    if term.endswith("ed") and len(term)>4: candidates.add(term[:-2])
    if term.endswith("s") and len(term)>4: candidates.add(term[:-1])
    return any(len(c)>=4 and re.search(rf"\b{re.escape(c)}\w*\b",text) for c in candidates)


def _relevance_score(topic,source):
    title=_clean(source.get("title","")).lower(); evidence=_clean(source.get("evidence_text") or source.get("abstract","")).lower()
    title_clean=" ".join(re.sub(r"[^a-z0-9\s]"," ",title).split()); evidence_clean=" ".join(re.sub(r"[^a-z0-9\s]"," ",evidence).split())
    terms=set(_tokenize(topic)); concepts=_concepts_from_text(topic)
    tc=_concepts_from_text(title_clean); ec=_concepts_from_text(evidence_clean)
    tcm=concepts&tc; ecm=concepts&ec; score=0; mt=set(); tm=em=0
    for term in terms:
        if _stem_like_match(term,title_clean): tm+=1; mt.add(term); score+=4
        elif _stem_like_match(term,evidence_clean): em+=1; mt.add(term); score+=1
    score+=len(tcm)*6+len(ecm-tcm)*2
    nt=_normalize_title(topic); ntitle=_normalize_title(title)
    if nt and nt in ntitle: score+=12
    toks=list(_tokenize(topic))
    for i in range(len(toks)-1):
        if toks[i]+" "+toks[i+1] in title_clean: score+=5
    if len(concepts)>=2:
        if len(tcm)>=2 or (len(tcm)>=1 and len(ecm)>=2): cls="strong"
        elif len(tcm)>=1 and len(ecm)>=1 or tm>=2: cls="moderate"
        else: cls="weak"
    else:
        cls="moderate" if tm>=2 or len(tcm)>=1 or (tm>=1 and em>=2) else "weak"
    domains={"bird","plants","space","ocean","human","technology","quantum"}; td=concepts&domains
    if td and not (tcm|ecm)&td: cls="mismatch"; score=0
    source.update({"matched_terms":sorted(mt),"topic_concepts":sorted(concepts),"title_concepts":sorted(tcm),"abstract_concepts":sorted(ecm),"title_match_count":tm,"abstract_match_count":em,"topic_concept_coverage":round(len(tcm|ecm)/max(len(concepts),1),3),"relevance_class":cls,"relevance_score":score})
    return score


def relevance_filter(topic,sources,label="STRICT TOPIC RELEVANCE FILTER"):
    print("="*80); print("ð¯ "+label); print("="*80)
    print("Topic concepts: "+(", ".join(sorted(_concepts_from_text(topic))) or "none"))
    out=[]
    for s in sources:
        score=_relevance_score(topic,s); title=s.get("title",""); cls=s.get("relevance_class")
        if cls in {"strong","moderate"}:
            out.append(s); print(f"â RELEVANT: {title}\n   Score: {score}\n   Class: {cls}")
        else: print(f"â REJECTED: {title}\n   Score: {score}\n   Class: {cls}")
    print(f"Relevant candidates: {len(out)}"); return out


def _authors_crossref(item):
    out=[]
    for a in item.get("author",[]):
        name=" ".join(x for x in (_clean(a.get("given","")),_clean(a.get("family",""))) if x)
        if name: out.append(name)
    return ", ".join(out)

def _authors_semantic(item):
    return ", ".join(_clean(a.get("name","")) for a in item.get("authors",[]) if _clean(a.get("name","")))

def _extract_year(item):
    for k in ("published-print","published-online","published","issued","created"):
        d=item.get(k,{})
        if isinstance(d,dict) and d.get("date-parts") and d["date-parts"][0]:
            try:return int(d["date-parts"][0][0])
            except Exception:pass
    return None

def _openalex_abstract_text(index):
    if not isinstance(index,dict): return ""
    words=[]
    for word,pos in index.items():
        if isinstance(pos,list):
            for p in pos:
                try: words.append((int(p),word))
                except Exception: pass
    words.sort(); return _clean_abstract(" ".join(w for _,w in words))

def _build_evidence_package(source):
    abstract=_clean_abstract(source.get("abstract",""))
    source["evidence_available"]=bool(abstract)
    source["evidence_type"]="abstract" if abstract else "metadata_only"
    source["evidence_quality"]=EVIDENCE_QUALITY_MODERATE if abstract else EVIDENCE_QUALITY_NONE
    source["evidence_text"]=abstract[:MAX_EVIDENCE_TEXT_CHARACTERS]
    source["evidence_notes"]=("Retrieved scholarly abstract; not full paper." if abstract else "No abstract/evidence retrieved; metadata is not evidence.")
    source["abstract"]=source["evidence_text"]
    return source


def search_crossref(topic):
    print("="*80); print("ð CROSSREF SEARCH"); print("="*80)
    data=_get(CROSSREF_URL,{"query.bibliographic":topic,"rows":MAX_CROSSREF_RESULTS,"select":"DOI,title,author,container-title,publisher,type,published,published-print,published-online,URL,abstract"},2,2)
    out=[]
    for item in data.get("message",{}).get("items",[]):
        title=_clean((item.get("title",[]) or [""])[0]); doi=_normalize_doi(item.get("DOI",""))
        if not title or not doi: continue
        out.append(_build_evidence_package({"source_database":"Crossref","title":title,"authors":_authors_crossref(item),"journal":_clean((item.get("container-title",[]) or [""])[0]),"publisher":_clean(item.get("publisher","")),"year":_extract_year(item),"doi":doi,"url":_clean(item.get("URL","")) or f"https://doi.org/{doi}","type":_clean(item.get("type","")),"publication_type":_clean(item.get("type","")),"abstract":_clean_abstract(item.get("abstract","")),"evidence_source":"Crossref abstract" if item.get("abstract") else "","metadata_verified":False,"evidence_verified":False,"verified":False}))
    print(f"Crossref results: {len(out)}"); return out


def search_semantic_scholar(topic):
    print("="*80); print("ð SEMANTIC SCHOLAR SEARCH"); print("="*80)
    try:data=_get(SEMANTIC_SCHOLAR_URL,{"query":topic,"limit":MAX_SEMANTIC_RESULTS,"fields":"title,authors,year,abstract,url,externalIds,publicationTypes,venue,citationCount"},SEMANTIC_RETRIES,SEMANTIC_BACKOFF_SECONDS)
    except Exception as e: print("â ï¸ Semantic Scholar unavailable:",e); return []
    out=[]
    for p in data.get("data",[]):
        title=_clean(p.get("title","")); ids=p.get("externalIds",{}) or {}; doi=_normalize_doi(ids.get("DOI",""))
        if not title or not doi: continue
        abstract=_clean_abstract(p.get("abstract","")); types=p.get("publicationTypes",[]) or []
        out.append(_build_evidence_package({"source_database":"Semantic Scholar","title":title,"authors":_authors_semantic(p),"journal":_clean(p.get("venue","")),"publisher":"","year":p.get("year"),"doi":doi,"url":f"https://doi.org/{doi}","semantic_scholar_url":_clean(p.get("url","")),"abstract":abstract,"publication_types":types,"publication_type":types[0] if types else "","citation_count":p.get("citationCount",0) or 0,"evidence_source":"Semantic Scholar abstract" if abstract else "","metadata_verified":False,"evidence_verified":False,"verified":False}))
    print(f"Semantic Scholar results: {len(out)}"); return out


def search_openalex(topic):
    print("="*80); print("ð OPENALEX SEARCH"); print("="*80)
    try:data=_get(OPENALEX_URL,{"search":topic,"per-page":MAX_OPENALEX_RESULTS},2,2)
    except Exception as e: print("â ï¸ OpenAlex search failed:",e); return []
    out=[]
    for item in data.get("results",[]):
        title=_clean(item.get("display_name","")); ids=item.get("ids",{}) or {}; doi=_normalize_doi(ids.get("doi",""))
        if not title or not doi: continue
        authors=[]
        for a in item.get("authorships",[]):
            n=_clean((a.get("author",{}) or {}).get("display_name",""));
            if n: authors.append(n)
        loc=item.get("primary_location",{}) or {}; si=loc.get("source",{}) or {}; abstract=_openalex_abstract_text(item.get("abstract_inverted_index"))
        out.append(_build_evidence_package({"source_database":"OpenAlex","title":title,"authors":", ".join(authors),"journal":_clean(si.get("display_name","")),"publisher":"","year":item.get("publication_year"),"doi":doi,"url":f"https://doi.org/{doi}","openalex_url":_clean(ids.get("openalex","")),"abstract":abstract,"publication_type":_clean(item.get("type","")),"citation_count":item.get("cited_by_count",0) or 0,"open_access":bool((item.get("open_access",{}) or {}).get("is_oa",False)),"evidence_source":"OpenAlex abstract" if abstract else "","metadata_verified":False,"evidence_verified":False,"verified":False}))
    print(f"OpenAlex results: {len(out)}"); return out


def _merge_sources(primary,secondary):
    for f in ("authors","journal","publisher","year","url","type","publication_type","semantic_scholar_url","openalex_url"):
        if not primary.get(f) and secondary.get(f): primary[f]=secondary[f]
    if len(_clean_abstract(secondary.get("abstract","")))>len(_clean_abstract(primary.get("abstract",""))):
        primary["abstract"]=_clean_abstract(secondary.get("abstract","")); primary["evidence_source"]=secondary.get("evidence_source","")
    primary["citation_count"]=max(primary.get("citation_count",0) or 0,secondary.get("citation_count",0) or 0)
    db=set(primary.get("source_databases",[])); db.update(x for x in (primary.get("source_database"),secondary.get("source_database")) if x); primary["source_databases"]=sorted(db)
    return _build_evidence_package(primary)


def deduplicate_sources(sources):
    by_doi={}; by_title={}; unique=[]
    for s in sources:
        doi=_normalize_doi(s.get("doi","")); title=_normalize_title(s.get("title","")); existing=by_doi.get(doi) if doi else by_title.get(title)
        if existing is not None: _merge_sources(existing,s); continue
        s["doi"]=doi; s["source_databases"]=[s.get("source_database","")]; unique.append(s)
        if doi: by_doi[doi]=s
        if title: by_title[title]=s
    return unique


def _identity_matches(source,returned_title,returned_doi,provider):
    expected=_normalize_doi(source.get("doi","")); returned=_normalize_doi(returned_doi)
    if not expected or not returned or expected!=returned:
        source["identity_error"]=f"{provider}: DOI mismatch or missing DOI."; return False
    sim=_title_similarity(source.get("title",""),returned_title); source["verified_title_similarity"]=round(sim,3)
    if sim<TITLE_SIMILARITY_MINIMUM:
        source["identity_error"]=f"{provider}: title mismatch; similarity {sim:.3f}."; return False
    return True


def verify_crossref_source(s):
    doi=_normalize_doi(s.get("doi",""))
    if not doi:return False
    try:
        item=_get(CROSSREF_URL+"/"+quote(doi,safe=""),retries=1,backoff=2).get("message",{}); rd=_normalize_doi(item.get("DOI","")); rt=_clean((item.get("title",[]) or [""])[0])
        if not _identity_matches(s,rt,rd,"Crossref"):return False
        s.update({"metadata_verified":True,"verified_title":rt,"doi":rd});
        if _authors_crossref(item):s["authors"]=_authors_crossref(item)
        if _clean((item.get("container-title",[]) or [""])[0]):s["journal"]=_clean((item.get("container-title",[]) or [""])[0])
        if _clean(item.get("publisher","")):s["publisher"]=_clean(item.get("publisher",""))
        if _extract_year(item):s["year"]=_extract_year(item)
        a=_clean_abstract(item.get("abstract",""))
        if a:s["abstract"]=a;s["evidence_source"]="Crossref abstract"
        s["verification"]="DOI and publication identity verified through Crossref."; return _build_evidence_package(s)
    except Exception as e:s["verification_error"]=str(e);return False


def verify_semantic_source(s):
    doi=_normalize_doi(s.get("doi",""))
    if not doi:return False
    try:
        d=_get(SEMANTIC_PAPER_URL+"/DOI:"+quote(doi,safe=""),{"fields":"title,authors,year,abstract,externalIds,venue,publicationTypes,citationCount"},SEMANTIC_RETRIES,SEMANTIC_BACKOFF_SECONDS); ids=d.get("externalIds",{}) or {}; rd=_normalize_doi(ids.get("DOI","") or doi); rt=_clean(d.get("title",""))
        if not _identity_matches(s,rt,rd,"Semantic Scholar"):return False
        s.update({"metadata_verified":True,"verified_title":rt,"doi":doi});
        if _authors_semantic(d):s["authors"]=_authors_semantic(d)
        if _clean(d.get("venue","")):s["journal"]=_clean(d.get("venue",""))
        if d.get("year"):s["year"]=d["year"]
        a=_clean_abstract(d.get("abstract",""))
        if a:s["abstract"]=a;s["evidence_source"]="Semantic Scholar abstract"
        s["citation_count"]=d.get("citationCount",s.get("citation_count",0)) or 0;s["verification"]="DOI and publication identity verified through Semantic Scholar.";return _build_evidence_package(s)
    except Exception as e:s["verification_error"]=str(e);return False


def verify_openalex_source(s):
    doi=_normalize_doi(s.get("doi",""))
    if not doi:return False
    try:
        d=_get(OPENALEX_URL+"/https://doi.org/"+quote(doi,safe=""),retries=1,backoff=2); ids=d.get("ids",{}) or {}; rd=_normalize_doi(ids.get("doi","") or doi); rt=_clean(d.get("display_name",""))
        if not _identity_matches(s,rt,rd,"OpenAlex"):return False
        s.update({"metadata_verified":True,"verified_title":rt,"doi":doi});
        if d.get("publication_year"):s["year"]=d["publication_year"]
        a=_openalex_abstract_text(d.get("abstract_inverted_index"))
        if a:s["abstract"]=a;s["evidence_source"]="OpenAlex abstract"
        s["openalex_citation_count"]=d.get("cited_by_count",0) or 0;s["openalex_id"]=_clean(d.get("id",""));s["verification"]="DOI and publication identity verified through OpenAlex.";return _build_evidence_package(s)
    except Exception as e:s["verification_error"]=str(e);return False


def enrich_from_semantic(s):
    doi=_normalize_doi(s.get("doi",""))
    if not doi:return s
    try:
        d=_get(SEMANTIC_PAPER_URL+"/DOI:"+quote(doi,safe=""),{"fields":"title,abstract,year,externalIds,publicationTypes,citationCount"},SEMANTIC_RETRIES,SEMANTIC_BACKOFF_SECONDS); a=_clean_abstract(d.get("abstract",""))
        if a:s["abstract"]=a;s["evidence_source"]="Semantic Scholar abstract"
        s["citation_count"]=d.get("citationCount",s.get("citation_count",0)) or 0
    except Exception as e:s["semantic_enrichment_error"]=str(e)
    return s


def enrich_from_openalex(s):
    doi=_normalize_doi(s.get("doi",""))
    if not doi:return s
    try:
        d=_get(OPENALEX_URL+"/https://doi.org/"+quote(doi,safe=""),retries=1,backoff=2); a=_openalex_abstract_text(d.get("abstract_inverted_index"))
        if a:s["abstract"]=a;s["evidence_source"]="OpenAlex abstract";s["openalex_enriched"]=True
        s["openalex_citation_count"]=d.get("cited_by_count",0) or 0;s["openalex_id"]=_clean(d.get("id",""))
    except Exception as e:s["openalex_enrichment_error"]=str(e)
    return s


def enrich_source(s):
    if _clean_abstract(s.get("abstract","")):return _build_evidence_package(s)
    s=enrich_from_semantic(s)
    if _clean_abstract(s.get("abstract","")):return _build_evidence_package(s)
    return _build_evidence_package(enrich_from_openalex(s))


def enrich_sources(sources):
    print("="*80);print("ð ENRICHING RESEARCH EVIDENCE");print("="*80);out=[]
    for i,s in enumerate(sources,1):
        print(f"Evidence {i}/{len(sources)}: {s.get('title','')}");s=enrich_source(s)
        if s.get("evidence_available"):
            print(f"â Evidence available ({len(s.get('evidence_text',''))} chars)");out.append(s)
        else:print("â No evidence available")
    return out


def _classify_study_design(s):
    text=(_clean(s.get("title",""))+" "+" ".join(_clean(x) for x in s.get("publication_types",[]) or [])).lower()
    if "systematic review" in text or "meta-analysis" in text or "meta analysis" in text:d="systematic_review_or_meta_analysis"
    elif "review" in text:d="review"
    elif "randomized controlled trial" in text or "randomised controlled trial" in text:d="randomized_trial"
    elif "clinical trial" in text or "controlled trial" in text:d="clinical_or_controlled_trial"
    elif "longitudinal" in text or "cohort" in text:d="observational_cohort"
    elif "cross-sectional" in text or "cross sectional" in text:d="cross_sectional"
    elif "case report" in text or "case study" in text:d="case_report_or_case_study"
    else:d="research_article_or_unspecified"
    s["study_design"]=d;return s


def mark_evidence_verified(sources):
    out=[]
    for s in sources:
        title=_clean(s.get("title","")); evidence=_clean_abstract(s.get("evidence_text",""))
        if s.get("metadata_verified") is not True:print(f"â Rejected unverified source: {title}");continue
        if len(evidence)<MIN_ABSTRACT_CHARACTERS:print(f"â Rejected insufficient evidence: {title}");continue
        if not _clean(s.get("authors","")) or not s.get("year") or not _normalize_doi(s.get("doi","")) or not _clean(s.get("url","")):
            print(f"â Rejected incomplete source metadata: {title}");continue
        doi=_normalize_doi(s["doi"]); expected=_generate_source_id(doi); existing=_clean(s.get("source_id",""))
        if existing and existing!=expected:print(f"â Rejected invalid source_id: {title}");continue
        s.update({"source_id":expected,"doi":doi,"abstract":evidence,"evidence_text":evidence,"evidence_available":True,"evidence_type":"abstract","evidence_quality":EVIDENCE_QUALITY_MODERATE,"evidence_verified":True,"verified":True,"verification_level":"DOI_METADATA_PLUS_ABSTRACT","evidence_verification":"DOI/publication identity verified and scholarly abstract retrieved."})
        _classify_study_design(s);out.append(s)
    return out


def limit_sources(sources):
    def key(s):
        citations=max(s.get("citation_count",0) or 0,s.get("openalex_citation_count",0) or 0)
        return (s.get("relevance_score",0),s.get("topic_concept_coverage",0),citations)
    return sorted(sources,key=key,reverse=True)[:MAX_EVIDENCE_SOURCES]


def validate_independent_sources(sources):
    dois={_normalize_doi(s.get("doi","")) for s in sources if _normalize_doi(s.get("doi",""))}
    if len(dois)<MIN_ACCEPTED_SOURCES:raise RuntimeError("RESEARCH FAILED: fewer than two distinct DOI-backed sources remain.")
    families={( _clean(s.get("publisher","")).lower(),_clean(s.get("journal","")).lower()) for s in sources}
    return {"distinct_doi_count":len(dois),"distinct_publisher_journal_pairs":len(families)}


def validate_source_ids(sources):
    seen=set()
    for s in sources:
        sid=_clean(s.get("source_id",""));doi=_normalize_doi(s.get("doi",""));title=s.get("title","")
        if not sid or not doi:raise RuntimeError(f"RESEARCH FAILED: source '{title}' missing source_id or DOI.")
        if sid!=_generate_source_id(doi):raise RuntimeError(f"RESEARCH FAILED: source ID mismatch for '{title}'.")
        if sid in seen:raise RuntimeError(f"RESEARCH FAILED: duplicate source_id {sid}.")
        seen.add(sid)
        if s.get("metadata_verified") is not True or s.get("evidence_verified") is not True or s.get("evidence_available") is not True or s.get("verified") is not True:raise RuntimeError(f"RESEARCH FAILED: source '{title}' failed verification flags.")
        if len(_clean(s.get("evidence_text","")))<MIN_ABSTRACT_CHARACTERS:raise RuntimeError(f"RESEARCH FAILED: source '{title}' has insufficient evidence text.")
    return True


def validate_research_package(package):
    if not isinstance(package,dict) or package.get("status")!="VERIFIED" or package.get("verified") is not True:raise RuntimeError("RESEARCH FAILED: invalid verified package.")
    sources=package.get("sources",[])
    if not isinstance(sources,list) or len(sources)<MIN_ACCEPTED_SOURCES:raise RuntimeError("RESEARCH FAILED: insufficient final sources.")
    validate_source_ids(sources)
    if any(s.get("relevance_class") not in {"strong","moderate"} for s in sources):raise RuntimeError("RESEARCH FAILED: irrelevant final source detected.")
    return True


def research_topic(topic):
    topic=_clean(topic)
    if not topic:raise RuntimeError("Research topic cannot be empty.")
    print("="*80);print("ð¬ MINT-YT-FACTORY RESEARCH v5.0");print("="*80);print(f"Topic: {topic}")
    all_sources=[]
    for fn in (search_crossref,search_semantic_scholar,search_openalex):
        try:all_sources.extend(fn(topic))
        except Exception as e:print(f"â ï¸ {fn.__name__} failed: {e}")
    candidates=deduplicate_sources(all_sources);print(f"Unique candidates: {len(candidates)}")
    if not candidates:raise RuntimeError("RESEARCH FAILED: no research candidates were found.")
    doi_candidates=[]
    for s in candidates:
        doi=_normalize_doi(s.get("doi",""))
        if not doi:print(f"â ï¸ REJECTED â NO DOI: {s.get('title','')}");continue
        s["doi"]=doi;s["source_id"]=_generate_source_id(doi);doi_candidates.append(s)
    if not doi_candidates:raise RuntimeError("RESEARCH FAILED: no DOI candidates.")
    relevant=relevance_filter(topic,doi_candidates)
    if not relevant:raise RuntimeError("RESEARCH FAILED: no sufficiently relevant sources found.")
    print("="*80);print("ð§ª VERIFYING DOI + PUBLICATION IDENTITY");print("="*80);verified=[]
    for i,s in enumerate(relevant,1):
        print(f"Checking source {i}/{len(relevant)}: {s.get('title','')}"); db=set(s.get("source_databases",[])); ok=verify_crossref_source(s)
        if not ok and "Semantic Scholar" in db:ok=verify_semantic_source(s)
        if not ok and "OpenAlex" in db:ok=verify_openalex_source(s)
        if ok:print("â DOI + IDENTITY VERIFIED");verified.append(s)
        else:print("â IDENTITY NOT VERIFIED")
    if not verified:raise RuntimeError("RESEARCH FAILED: no DOI-verified sources remained.")
    evidence=mark_evidence_verified(enrich_sources(verified))
    if not evidence:raise RuntimeError("RESEARCH FAILED: no evidence-backed sources remained.")
    evidence=relevance_filter(topic,evidence,label="FINAL EVIDENCE RELEVANCE CHECK")
    evidence=[s for s in evidence if s.get("evidence_verified") is True]
    evidence=limit_sources(evidence)
    if len(evidence)<MIN_ACCEPTED_SOURCES:raise RuntimeError(f"RESEARCH FAILED: only {len(evidence)} evidence-backed relevant source(s) found; need {MIN_ACCEPTED_SOURCES}.")
    diversity=validate_independent_sources(evidence);validate_source_ids(evidence)
    package={"topic":topic,"status":"VERIFIED","verified":True,"verified_at":int(time.time()),"verification_policy":{"minimum_sources":MIN_ACCEPTED_SOURCES,"metadata_required":True,"doi_required":True,"abstract_required":True,"minimum_abstract_characters":MIN_ABSTRACT_CHARACTERS,"metadata_only_sources_allowed":False,"evidence_verification_required":True,"strict_topic_relevance":True,"final_relevance_recheck":True,"full_text_required":False,"abstract_is_full_text":False,"identity_verification_required":True,"title_identity_similarity_minimum":TITLE_SIMILARITY_MINIMUM,"authoritative_source_id_required":True,"source_id_algorithm":"sha256(normalized_doi)[:12]","gemini_used_for_evidence":False},"source_count":len(evidence),"evidence_source_count":len(evidence),"source_diversity":diversity,"sources":evidence}
    validate_research_package(package)
    print("="*80);print("â RESEARCH VERIFIED");print(f"Evidence-backed relevant sources: {len(evidence)}")
    for i,s in enumerate(evidence,1):print(f"{i}. {s['title']}\n   Source ID: {s['source_id']}\n   DOI: {s['doi']}\n   Evidence: {s.get('evidence_source','')}\n   Quality: {s.get('evidence_quality','')}\n   Study design: {s.get('study_design','')}\n   Relevance: {s.get('relevance_class','')} ({s.get('relevance_score',0)})")
    print("="*80);return package


def save_research(research,output_path):
    directory=os.path.dirname(output_path)
    if directory:os.makedirs(directory,exist_ok=True)
    with open(output_path,"w",encoding="utf-8") as f:json.dump(research,f,indent=2,ensure_ascii=False)
    return output_path


if __name__=="__main__":
    if len(sys.argv)<2:print('Usage: python research.py "your topic"');sys.exit(1)
    try:
        result=research_topic(" ".join(sys.argv[1:]));output=os.path.join("output","research_test.json");save_research(result,output);print(f"ð Research saved: {output}")
    except Exception as e:print("â RESEARCH FAILED:",e);sys.exit(1)