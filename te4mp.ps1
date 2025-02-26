for ($n=1; $n -le 50; $n++) {
    Write-Host "Running with -n $n"
    python .\loadSpinData.py -n $n -t quic-go ..\67060052d5618f423aa7f10d\CCA_variants_dataset\go-test\l2.7b17d33_t1739253383\
}
