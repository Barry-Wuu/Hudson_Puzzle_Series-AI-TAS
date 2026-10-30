// Offline renderer: SDAT sequence -> stereo WAV, using kode54 SSEQPlayer core
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "SDAT.h"
#include "Player.h"

int main(int argc, char **argv)
{
    if (argc < 5) { fprintf(stderr, "usage: %s sdat seqIndex seconds out.wav [interp=1] [rate=32768]\n", argv[0]); return 1; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("open sdat"); return 1; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    std::vector<uint8_t> data(sz);
    if (fread(data.data(), 1, sz, f) != (size_t)sz) { perror("read"); return 1; }
    fclose(f);
    uint32_t idx = (uint32_t)strtoul(argv[2], NULL, 0);
    double secs = atof(argv[3]);
    int interp = argc > 5 ? atoi(argv[5]) : 1;   // 1=linear (NDS HW-accurate-ish)
    uint32_t rate = argc > 6 ? strtoul(argv[6], NULL, 0) : 32768;

    PseudoFile file;
    static std::vector<uint8_t> sdata = std::move(data);
    file.data = &sdata;
    SDAT sdat(file, idx);
    if (!sdat.sseq) { fprintf(stderr, "no sseq\n"); return 1; }
    if (!sdat.sbnk) { fprintf(stderr, "no sbnk\n"); return 1; }

    Player player;
    player.sampleRate = rate;
    player.interpolation = static_cast<Interpolation>(interp);
    if (!player.Setup(sdat.sseq.get())) { fprintf(stderr, "setup failed\n"); return 1; }

    unsigned total = (unsigned)(secs * rate);
    std::vector<uint8_t> buf(total * 4);
    unsigned pos = 0;
    while (pos < buf.size()) {
        unsigned n = std::min<unsigned>(rate / 10, buf.size() - pos);
        player.GenerateSamples(buf, pos, n);
        pos += n;
    }
    FILE *o = fopen(argv[4], "wb");
    if (!o) { perror("out"); return 1; }
    uint32_t dr = rate, bps = 16, ch = 2;
    uint32_t dsz = buf.size(), fsz = 36 + dsz;
    fwrite("RIFF", 1, 4, o); fwrite(&fsz, 4, 1, o); fwrite("WAVEfmt ", 8, 1, o);
    uint32_t fe = 16; uint16_t fm = 1; fwrite(&fe, 4, 1, o); fwrite(&fm, 2, 1, o);
    fwrite(&ch, 2, 1, o); fwrite(&dr, 4, 1, o); uint32_t br = dr * ch * bps / 8; fwrite(&br, 4, 1, o);
    uint16_t ba = ch * bps / 8; fwrite(&ba, 2, 1, o); fwrite(&bps, 2, 1, o);
    fwrite("data", 1, 4, o); fwrite(&dsz, 4, 1, o); fwrite(buf.data(), 1, dsz, o);
    fclose(o);
    fprintf(stderr, "wrote %s (%u samples)\n", argv[4], total);
    return 0;
}
