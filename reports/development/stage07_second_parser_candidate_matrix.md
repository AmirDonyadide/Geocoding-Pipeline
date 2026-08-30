# Stage 7 second-parser public eligibility review

This public-only review selects **DeepParse 0.10.0 with the BPEmb-attention
model** for exactly one controlled, non-authoritative comparison. No protected
candidate, Stage 6 artifact, HOLDOUT artifact, production artifact, or
authoritative Stage 7 output was accessed during this gate.

## Selection

The selected package source is DeepParse tag `0.10.0`, commit
`5b17c0bccd6773044f8a61da68a7b8c91c4fd1e8`. The preliminary model identity is
official repository `deepparse/bpemb-attention` at immutable revision
`4af74dad1d547804dfc2de8f40fb23fbbec5b811`. The diagnostic will use the
attention LSTM sequence tagger, multilingual BPEmb `multi` embeddings with
vocabulary size 100,000 and dimension 300, CPU evaluation, batch size one,
zero data-loader workers, probabilities enabled, hyphen splitting disabled,
and no caller-supplied preprocessors.

DeepParse is the only screened project that combines a maintained general
multinational parser, structured token labels, published offline operation,
and pinnable public code/model assets. It emits the native labels
`StreetNumber`, `StreetName`, `Unit`, `Municipality`, `Province`, `PostalCode`,
`Orientation`, and `GeneralDelivery`, plus per-token probabilities when
requested. SAFE will preserve the ordered token/tag/probability stream and the
exact candidate; it will not collapse it to the package's convenience
dictionary.

The eligibility result is deliberately qualified:

- official DeepParse data provenance states that its multinational address
  data were generated from libpostal data, so the second model is not an
  independently labelled scientific ground truth and may inherit correlated
  errors;
- direct address-parser evidence is strong for South Korea/Hangul, while Japan
  is a poor-performing zero-shot country;
- Lao, Thai, and Hebrew are represented in the underlying multilingual BPEmb
  language set, but no direct DeepParse address evaluation for those languages
  was found; and
- BPEmb internally lowercases and replaces digits with zero for embedding
  lookup. SAFE will still pass the exact accepted lowercase candidate, retain
  it exactly, and add no preprocessing. This fixed internal representation is
  part of the frozen parser identity, not a SAFE rewrite.

These limitations make the 120-case experiment necessary; they do not
predeclare improvement.

## Public candidate matrix

| Candidate | Approach / output | Offline and license | Relevant script evidence | Decision |
| --- | --- | --- | --- | --- |
| DeepParse 0.10.0 BPEmb-attention | Attention LSTM token tagger; eight address labels plus probabilities | Offline after public asset freeze; DeepParse LGPL-3.0, BPEmb code MIT, address data MIT; model card has no separate license field | Direct South Korea/Hangul example and evaluation; weak Japan/Han zero-shot evidence; BPEmb-level Lao/Thai/Hebrew coverage only | **Selected with limitations** |
| Pelias parser `f880898` | Rules, dictionaries, patterns, and composite query classifiers | Offline Node.js; MIT | No substantiated coverage for the five required scripts | Rejected |
| usaddress 0.5.16 | CRF with detailed US component labels | Offline Python; MIT | Explicitly United States only | Rejected |
| iLib address 1.0.3 | Locale heuristics yielding country/region/locality/postcode/streetAddress | Offline with locale data; Apache-2.0 | Korean and Asian-order examples exist, but output leaves the relevant subaddress as a coarse `streetAddress`; no Lao/Thai/Hebrew evidence | Rejected |
| Swift ISO 20022 structuring `916deca` | CRF, fuzzy matching, and references | Offline after reference acquisition; project-specific license | Extracts town and country only | Rejected |
| Microsoft Recognizers-Text `da7edcf` | Multilingual number/unit/date/time/sequence recognizers | Offline; MIT | Not a free-form postal-address component parser | Rejected |
| Google libaddressinput `81eb962` | Country metadata for address forms and validation | Local libraries plus address metadata; Apache-2.0 code, CC-BY-4.0 data | Worldwide formatting metadata, not free-form parsing | Rejected |

DeepParse was preferred over its FastText configurations because its BPEmb
representation is explicitly multilingual and the attention model has the
strongest published BPEmb zero-shot result for Japan. CPU execution avoids a
GPU/backend routing variable. The final diagnostic bundle will separately pin
and hash every package, checkpoint, embedding, tokenizer, runtime dependency,
Python runtime, and license/notice file before protected inference. Public
downloads will complete before any protected input is opened, and protected
inference will permit zero network calls.

## Sources

Primary project and paper sources used for the screen:

- [DeepParse repository](https://github.com/GRAAL-Research/deepparse),
  [parser documentation](https://deepparse.org/parser.html), and
  [NLP-OSS paper](https://aclanthology.org/2023.nlposs-1.3/)
- [DeepParse address-data provenance](https://github.com/GRAAL-Research/deepparse-address-data)
- [BPEmb repository](https://github.com/bheinzerling/bpemb) and
  [LREC paper](https://aclanthology.org/L18-1473/)
- [official BPEmb-attention model repository](https://huggingface.co/deepparse/bpemb-attention)
- [Pelias parser](https://github.com/pelias/parser)
- [usaddress](https://github.com/datamade/usaddress)
- [iLib monorepo](https://github.com/iLib-js/ilib-mono)
- [Swift ISO 20022 address structuring](https://github.com/Swift-SC/iso20022-address-structuring)
- [Microsoft Recognizers-Text](https://github.com/microsoft/Recognizers-Text)
- [Google libaddressinput](https://github.com/google/libaddressinput)

This selection authorizes only public bundle construction and the owner-approved
120-case diagnostic. It does not select a Stage 7 redesign, alter the frozen
libpostal baseline, or authorize a new authoritative registry.
