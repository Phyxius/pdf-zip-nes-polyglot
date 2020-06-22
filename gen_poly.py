#!/usr/bin/env python3

from __future__ import print_function
import argparse, sys, zipfile, ntpath
import os.path
import shutil
import struct
import base64

from io import BytesIO

def errprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def filelike_size(f):
    old_file_position = f.tell()
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(old_file_position, os.SEEK_SET)
    return size

def gen_whitespace_program(data_to_print):
    data_to_print += "\n"
    # https://stackoverflow.com/questions/10321978/integer-to-bitfield-as-a-list
    def bitfield(n):
        return "".join(['\t' if digit=='1' else ' ' for digit in bin(n)[2:]]).rjust(8, ' ')
    program = ""
    for c in data_to_print:
        program += '  ' + bitfield(ord(c)) + "\n"
        program += "\t\n  " # print
    program += "\n\n\n"
    return program

def gen_bf_program(data_to_print):
    data_to_print += "\n"
    # translated from https://codegolf.stackexchange.com/a/12477
    program = ""
    singles = ""
    tens = ""
    goBack = ""
    program += 10 * "+"
    program += "[>"
    program += 10 * "+"
    program += "["
    for c in (ord(c) for c in data_to_print):
        program += ">"
        program += (c // 100) * "+"
        tens += ">"
        if (c - (c//100)*100)//10 <= 5:
            tens += ((c - (c//100)*100)//10) * "+"
        else:
            program += "+"
            tens += (10 - (c - (c//100)*100)//10) * "-"
        singles += ">"
        if c % 10 <= 5:
            singles += (c%10) * "+"
        else: 
            tens += "+"
            singles += (10 - (c%10)) * "-"
        singles += "."
        goBack += "<"
    goBack += "-"
    program += goBack
    program += "]"
    program += tens
    program += "<"
    program += goBack
    program += "]>"
    program += singles
    program += ">>>+[>,]" #loop forever at the end
    return program

class InMemoryZipFile(object):
    #mostly courtesy of Justin Ethier and @ruamel, stackoverflow.com/questions/2463770
    def __init__(self, file_name=None, compression=zipfile.ZIP_DEFLATED, debug=0):
        # Create the in-memory file-like object
        if hasattr(file_name, '_from_parts'):
            self._file_name = str(file_name)
        else:
            self._file_name = file_name

        self.in_memory_data = BytesIO()
        # Create the in-memory zipfile
        self.in_memory_zip = zipfile.ZipFile(self.in_memory_data, "w", compression, False )
        self.in_memory_zip.debug = debug
        self.compression_map = dict()
        self.compression = compression

    def append(self, filepath_to_zip, compress_type):
        '''Appends the file at path filepath_to_zip to the in-memory 
        zip, compressing according to the compress_type'''

        # Write the file to the in-memory zip
        self.in_memory_zip.write(filepath_to_zip, compress_type=compress_type)
        self.compression_map[filepath_to_zip] = compress_type

        return self #for daisy-chaining

    def appendStr(self, filename_in_zip, file_contents, compress_type):
        '''Appends a file with name filename_in_zip and contents of
        file_contents to the in-memory zip.'''
        self.in_memory_zip.writestr(filename_in_zip, file_contents, compress_type=compress_type)
        self.compression_map[filename_in_zip] = compress_type
        return self   # so you can daisy-chain

    def write_to_file(self, filename):
        '''Writes the in-memory zip to a file.'''
        # Mark the files as having been created on Windows so that
        # Unix permissions are not inferred as 0000
        for zfile in self.in_memory_zip.filelist:
            zfile.create_system = 0

        self.in_memory_zip.close()
        with open(filename, 'xb') as f:
            f.write(self.data)

    def close_and_return_data(self): #there's no coming back
        '''Closes the ZIP file, and make last required adjustments. 
        After calling this method, there's no coming back. The only
        thing you can do is writing the ZIP.'''
        # Mark the files as having been created on Windows so that
        # Unix permissions are not inferred as 0000
        for zfile in self.in_memory_zip.filelist:
            zfile.create_system = 0

        self.in_memory_zip.close()
        return self.data

    @property
    def data(self):
        return self.in_memory_data.getvalue()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._file_name is None:
            return
        self.write_to_file(self._file_name)

    def delete(self, file_name):
        """
        zip_file can be a string or a zipfile.ZipFile object, the latter will be closed
        any name in file_names is deleted, all file_names provided have to be in the ZIP
        archive or else an IOError is raised
        """
        new_in_memory_data = BytesIO()
        new_in_memory_zip = zipfile.ZipFile( new_in_memory_data, "w", self.compression, False )

        for l in self.in_memory_zip.infolist():
            if l.filename == file_name:
                continue
            new_in_memory_zip.writestr(l.filename, self.in_memory_zip.read(l.filename), compress_type=self.compression_map[l.filename])

        self.in_memory_zip = new_in_memory_zip
        self.in_memory_data = new_in_memory_data

    def delete_from_zip_file(self, pattern=None, file_names=None):
        """
        zip_file can be a string or a zipfile.ZipFile object, the latter will be closed
        any name in file_names is deleted, all file_names provided have to be in the ZIP
        archive or else an IOError is raised
        """
        if pattern and isinstance(pattern, string_type):
            import re
            pattern = re.compile(pattern)
        if file_names:
            if not isinstance(file_names, list):
                file_names = [str(file_names)]
            else:
                file_names = [str(f) for f in file_names]
        else:
            file_names = []
        with zipfile.ZipFile(self._file_name) as zf:
            for l in zf.infolist():
                if l.filename in file_names:
                    file_names.remove(l.filename)
                    continue
                if pattern and pattern.match(l.filename):
                    continue
                self.append(l.filename, zf.read(l))
            if file_names:
                raise IOError('[Errno 2] No such file{}: {}'.format(
                    '' if len(file_names) == 1 else 's',
                    ', '.join([repr(f) for f in file_names])))




parser = argparse.ArgumentParser(description='Generate a ZIP/PDF/Whatever polyglot file, with a cleartext message embedded (and instructions to output this message included). The `whatever` may be, for instance, a NES game file - it is added before the PDF.')
parser.add_argument('--out', dest='out_path', action='store', help='set the path of the resulting file', required=True)
parser.add_argument('--in', dest='in_path', action='store', help='path of the PDF to which to append', required=True)
parser.add_argument('--zip', dest='zip_array', action='store', nargs='+', help='path(s) to the file(s) going to be zipped and included in the PDF', required=True)
parser.add_argument('--html', dest='html_path', action='store', help='path to the HTML file', required=True)
parser.add_argument('--jpeg', dest='jpeg_path', action='store', help='path to the JPEG file, that will be added before the PDF', required=True)
parser.add_argument('--tar', dest='tar', action='store', help='path to a tar file that will be added after the JPEG data')
parser.add_argument('--ws-print', dest='ws_data', action='store', help='Data that will be printed when the file is run as a Whitespace program', required=True)
parser.add_argument('--bf-print', dest='bf_data', action='store', help='Data that will be printed when the file is run as a Brainfuck program', required=True)

def main():
    args = parser.parse_args()

    out_path = args.out_path
    tempout_path = out_path + ".temp"
    in_path = args.in_path
    zip_array = args.zip_array
    html_path = args.html_path
    jpeg_path = args.jpeg_path
    tar_path = args.tar
    ws_data = gen_whitespace_program(args.ws_data).encode()
    bf_data = gen_bf_program(args.bf_data).encode()

    if os.path.exists(out_path):
        errprint("File " + out_path + " ALREADY EXISTS, gonna overwrite !!!!!!!")
        #exit(1)

    with open(tempout_path, 'xb') as outfile:
        outfile.write(b'\xFF\xD8') # JPEG header
        custom_chunk = ws_data + bf_data + b"<!--"
        padding_length = 512 - (len(custom_chunk) + 6) % 512 - 4 # header length
        custom_chunk += b'F' * padding_length
        outfile.write(b'\xFF\xEA')
        outfile.write(struct.pack('>h', len(custom_chunk) + 2)) #write length
        # pad until the tar header will be at a multiple of 500 bytes
        outfile.write(custom_chunk)
        with open(tar_path, 'rb') as tar_file:
            tar = tar_file.read()
            outfile.write(b'\xFF\xEA')
            outfile.write(struct.pack('>h', len(tar) + 2)) #write length
            outfile.write(tar)
        with open(jpeg_path, 'rb') as jpeg:
            if jpeg.read(2) != b'\xFF\xD8': raise NotImplementedError()
            outfile.write(jpeg.read())
        with open(html_path, 'rb') as html_file:
            html = f"""
                --><html><script language='Javascript'>
                page="{base64.b64encode(html_file.read()).decode("UTF-8")}";
                document.getElementsByTagName("html")[0].innerHTML=window.atob(page)
                </script></html><!--
            """
            outfile.write(b'\xFF\xEA') #application-specific chunk 
            outfile.write(struct.pack('>h', len(html) + 2)) #write length
            outfile.write(html.encode('UTF8'))
        with InMemoryZipFile() as memzip:
            memzip.append(in_path, compress_type=zipfile.ZIP_STORED)
            for file_to_zip in zip_array:
                memzip.append(file_to_zip, compress_type=zipfile.ZIP_DEFLATED) #deflated
            size_of_zipped = filelike_size(memzip.in_memory_data)

            outfile.write(memzip.close_and_return_data())

    print("Now fixing ZIP file : ")
    fix_command = "zip -Fv " + tempout_path + " --out " + out_path #this fixes the offsets in the pdf/zip polyglot file, otherwise zip will complain (albeit correctly performing its work) when unzipping
    os.system(fix_command)
    os.remove(out_path + ".temp")

if __name__ == '__main__':
    main()
