// Stage 10's narrow C ABI over the exact locked ICU4C 77.1 build.
// No I/O, environment lookup, locale selection, fallback, or protected logging.
#include <unicode/translit.h>
#include <unicode/uniset.h>
#include <unicode/ustring.h>
#include <unicode/ulocdata.h>
#include <unicode/uchar.h>
#include <unicode/uversion.h>
#include <unicode/udata.h>
#include <cstdint>
#include <limits>
#include <memory>
#include <new>

using icu::Transliterator;
using icu::UnicodeString;
using icu::UnicodeSet;

static const char *additional_pattern(int32_t script) noexcept {
    return script == 1 ? "[[[:Greek:][:Inherited:]]&[[:L:][:M:]]]"
                       : "[[[:Cyrillic:][:Inherited:]]&[[:L:][:M:]]]";
}

extern "C" {
// Public build verification: enumerate the very same additional input filter
// used below, so pinned Script/U16 category tables can independently check it.
int32_t safe_stage10_filter_table(int32_t script, uint8_t *output,
                                 int32_t capacity) noexcept {
    if ((script != 1 && script != 2) || !output || capacity != 0x110000)
        return U_ILLEGAL_ARGUMENT_ERROR;
    try {
        UErrorCode status = U_ZERO_ERROR;
        UnicodeSet filter(UnicodeString::fromUTF8(additional_pattern(script)), status);
        if (U_FAILURE(status)) return status;
        for (int32_t cp = 0; cp < capacity; ++cp) output[cp] = filter.contains(cp);
        return U_ZERO_ERROR;
    } catch (...) { return U_MEMORY_ALLOCATION_ERROR; }
}

int32_t safe_stage10_versions(uint8_t *icu, uint8_t *unicode, uint8_t *cldr) noexcept {
    if (!icu || !unicode || !cldr) return U_ILLEGAL_ARGUMENT_ERROR;
    u_getVersion(icu);
    u_getUnicodeVersion(unicode);
    UErrorCode status = U_ZERO_ERROR;
    // Only the statically linked and hash-locked data is available. Never
    // read alternate ICU_DATA files or runtime-installed transform resources.
    udata_setFileAccess(UDATA_NO_FILES, &status);
    if (U_FAILURE(status)) return status;
    ulocdata_getCLDRVersion(cldr, &status);
    return status;
}

void *safe_stage10_open(int32_t script, int32_t *error) noexcept {
    if (!error) return nullptr;
    *error = U_ILLEGAL_ARGUMENT_ERROR;
    if (script != 1 && script != 2) return nullptr;
    try {
        const char *id = script == 1 ? "Grek-Latn" : "Cyrl-Latn";
        UErrorCode status = U_ZERO_ERROR;
        std::unique_ptr<Transliterator> transform(Transliterator::createInstance(
            UnicodeString::fromUTF8(id), UTRANS_FORWARD, status));
        if (U_FAILURE(status) || !transform) {
            *error = U_FAILURE(status) ? status : U_MEMORY_ALLOCATION_ERROR;
            return nullptr;
        }
        if (transform->getID() != UnicodeString::fromUTF8(id)) return nullptr;
        auto additional = std::make_unique<UnicodeSet>(UnicodeString::fromUTF8(additional_pattern(script)), status);
        if (U_FAILURE(status)) { *error = status; return nullptr; }
        if (const auto *original = transform->getFilter()) {
            UnicodeString original_pattern;
            original->toPattern(original_pattern, true);
            UnicodeSet original_set(original_pattern, status);
            if (U_FAILURE(status)) { *error = status; return nullptr; }
            additional->retainAll(original_set);
        }
        transform->adoptFilter(additional.release());
        *error = U_ZERO_ERROR;
        return transform.release();
    } catch (...) {
        *error = U_MEMORY_ALLOCATION_ERROR;
        return nullptr;
    }
}

void safe_stage10_close(void *handle) noexcept {
    delete static_cast<Transliterator *>(handle);
}

// Caller provides valid UTF-16; Python encodes strictly. The whole string is
// processed once per call. BUFFER_OVERFLOW reports the exact required capacity.
int32_t safe_stage10_transform(void *handle, const char16_t *input,
                             int32_t length, char16_t *output,
                             int32_t capacity, int32_t *required) noexcept {
    if (!handle || !input || !required || length < 0 || capacity < 0)
        return U_ILLEGAL_ARGUMENT_ERROR;
    try {
        UnicodeString value(input, length);
        if (value.isBogus()) return U_MEMORY_ALLOCATION_ERROR;
        static_cast<Transliterator *>(handle)->transliterate(value);
        if (value.isBogus()) return U_MEMORY_ALLOCATION_ERROR;
        *required = value.length();
        if (value.length() > capacity) return U_BUFFER_OVERFLOW_ERROR;
        UErrorCode status = U_ZERO_ERROR;
        value.extract(output, capacity, status);
        return status;
    } catch (...) {
        return U_MEMORY_ALLOCATION_ERROR;
    }
}
}
