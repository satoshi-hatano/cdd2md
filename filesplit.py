import os

def splitfile(fname:str, fn_start, fn_end, chunk_count:int):
    def filename_with_number(fname, number)->str:
        dir = os.path.dirname(fname)
        name_and_suffix = os.path.basename(fname).split('.')
        name_and_suffix[0] += str(number)
        return os.path.join(dir, '.'.join(name_and_suffix))
        
    with open(fname, "r", encoding="utf-8") as f:
        recording = False
        chunk = ''
        chunks = 0
        files = 0
        for line in f:
            if not recording:
                if not fn_start(line):
                    continue
                recording = True
            chunk += line
            if fn_end(line):
                recording = False
                chunks += 1
                if chunks == chunk_count:
                    with open(filename_with_number(fname, files), 'w', encoding='utf-8') as out:
                        out.write(chunk)
                    chunks = 0
                    chunk = ''
                    files += 1
        if chunk:
            with open(filename_with_number(fname, files), 'w', encoding='utf-8') as out:
                out.write(chunk)


# main
if __name__ == "__main__":
    def recording_on(s:str)->bool:
        return '<begin>' in s

    def recording_off(s:str)->bool:
        return '<end>' in s

    filename = '/home/shatano/cdd2md/foo.txt'
    splitfile(filename, recording_on, recording_off, 2)
