import errno
import xml.etree.ElementTree as ET
import urllib.parse
import re
import os, shutil  # make dir and copy files
import base64
import sys, getopt
# lxml is only used for cleaning the CDATA html. Con: not part of Python default install
import lxml
from lxml.html import fromstring, tostring, clean

"""
   todo: numeric tolerances should be converted to a range in numeric QT question. 
   <outcomeDeclaration identifier="SCORE" cardinality="single" baseType="float" normalMinimum="0" normalMaximum="9"/>
   <responseDeclaration identifier="RESPONSE" cardinality="single" baseType="float">
   <responseDeclaration identifier="RESPONSE" cardinality="multiple" baseType="float">
   <responseDeclaration baseType="string" cardinality="single" identifier="RESPONSE">
   todo: answer fraction="0" format="moodle_auto_format"> what to do with those answers in TVO grading? 
   todo: feedback correct/wrong is not always copied from moodle 
   todo: move ElementTree to lxml, don't use both
   Note: name of the question xml file need not match the identifier in the assessmentItem but it can be the same
   
"""

## xml namespaces
ns = {'imscp':  'http://www.imsglobal.org/xsd/imscp_v1p1',
      'imsmd':  'http://www.imsglobal.org/xsd/imsmd_v1p2',
      'imsqti': 'http://www.imsglobal.org/xsd/imsqti_v2p0',
      'xml':    'http://www.w3.org/XML/1998/namespace',
      'xhtml':  'http://www.w3.org/1999/xhtml'
      }

"""
Not producing manifest.xml - not needed for import?... depends on tool.
"""
def produceManifest():
    # mf = ET.ElementTree;
    ET.register_namespace('imscp', ns['imscp'])  # prefix,uri
    ET.register_namespace('imsmd', ns['imsmd'])
    ET.register_namespace('imsqti', ns['imsqti'])
    ET.register_namespace('xhtml', ns['xhtml'])
    mf = ET.parse('imsmanifest.xml')
    newmf = ET.parse("newmanifest.xml");
    newroot = newmf.getroot()
    elem = newroot.find('imscp:resources', ns)
    resource = elem.find('imscp:resource', ns)
    metadata = resource.find('imscp:metadata', ns)
    #   ET.dump(metadata)
    lom = metadata.find('imsmd:lom', ns)
    # todo not finished creating manifest


def readMoodle(inputfile, outputfolder):
    tree = ET.parse(inputfile)
    root = tree.getroot()
    convertix = 20000  # just a starting number for the question files
    curcategory = 'top'
    for q in root.findall("question"):
        convertix = convertix + 1
        qtype = q.attrib['type']
        #print("moodle qtype " + qtype)
        if qtype == 'category':
            ## create the category folder
            curcategory = parseCategory(q, outputfolder)
            continue
        # pass category to each q - todo check outputfoldername
        q.set('qcategory', curcategory)
        prefix = getprefix(qtype)
        q.set('convertix', prefix + str(convertix))
        qt = q.find("questiontext/text")
        ### fix html to correct xhtml
        qt.text = fixHtmlText(qt.text, convertix, prefix)
        ## Short answer is Fill In Blank in QTI with multiple possible correct answers
        if qtype == 'shortanswer' or qtype == 'numerical' or qtype == 'essay':
            produceFIBQuestion(q, qtype, outputfolder)
            continue
        if qtype == 'multichoice':
            produceMCQuestion(q, outputfolder)


def getprefix(qtype):
    prefix = 'AAA_ERROR'
    if qtype == 'shortanswer':
        prefix = 'MSHORT_'
    if qtype == 'numerical':
        prefix = 'NUMERIC_'
    if qtype == 'essay':
        prefix = 'ESSAY_'
    if qtype == 'multichoice':
        prefix = "MULTI_"
    return prefix


"""
<single>true</single> in Moodle defines single choice answer -> 
responseDeclaration identifier="RESPONSE" cardinality="single" in QT
basetype and maxChoices are important
"""
def produceMCQuestion(moodlemc, outputfolder):
    ET.register_namespace('', "http://www.imsglobal.org/xsd/imsqti_v2p1")  # no ns0 namespaces here
    tvmc = ET.fromstring(str(
        '<assessmentItem adaptive="false" timeDependent="false" toolName="Moodle_jand" toolVersion="1.2.3" xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1"></assessmentItem>'))
    # get (random) question number for id
    qid = moodlemc.get('convertix')
    tvmc.set('identifier', qid)
    title = moodlemc.find('name/text').text
    tvmc.set('title', title)
    m_qtext = moodlemc.find('questiontext/text').text  # the modified moodle qtext
    ## possible answers (values in correctresponse QTI)
    responseDeclaration = ET.SubElement(tvmc, 'responseDeclaration',
                                        {'identifier': 'RESPONSE', 'cardinality': 'to-be-set',
                                         'baseType': 'identifier'})
    if moodlemc.find('single').text == 'true':
        responseDeclaration.set('cardinality', 'single')
        singleChoice = True
    else:
        responseDeclaration.set('cardinality', 'multiple')
        singleChoice = False
    ## create correctresponse values as alt_1001 label id's
    rd = ET.SubElement(responseDeclaration, 'correctResponse')
    correctlist = []
    answerindex = 999  ## ID's alt just-a-number
    adict = {}
    for a in moodlemc.findall('answer'):
        answerindex = answerindex + 1
        if int(a.attrib['fraction']) > 10:  ## assume no smaller correct answers?
            correctlist.append(answerindex)
            value = ET.SubElement(rd, 'value')
            value.text = "alt_" + str(answerindex)
        at = a.find('text').text
        #  if a.attrib['format'] == "html":  print("html answer format")
        adict[answerindex] = at  # dictionary

    od = ET.SubElement(tvmc, 'outcomeDeclaration',
                       {'identifier': "SCORE", 'cardinality': "single", 'baseType': "float", 'normalMinimum': "0",
                        'normalMaximum': "1"})
    ## itembody generation
    ib = ET.SubElement(tvmc, 'itemBody')
    ## ramdom textblockid
    div1 = ET.SubElement(ib, 'div', {'id': "textBlockId_8881", 'class': "textblock tvblock tvcss_1"})
    ### trick: multiple html tags in comment
    qtext = ET.Comment('-->\n' + m_qtext + '\n<!--')
    div1.append(qtext)  # the question
    ci = ET.SubElement(ib, 'choiceInteraction', {'class': "EenKolom", 'responseIdentifier': "RESPONSE",
                                                 'shuffle': "true", 'maxChoices': "1"})
    ## fix maxchoices for many-choices
    if not singleChoice:
        ci.set('maxChoices', '0')
    # add simplechoices like these:
    # <simpleChoice identifier="alt_2802">
    #    <div id="textBlockId_830" class="textblock tvblock tvcss_1">
    #      <div class="rte_zone tveditor1">alter een goed</div>
    #    </div>
    # again iter over all answers
    answerindex = 999
    for a in moodlemc.findall('answer'):
        answerindex = answerindex + 1
        at = a.find('text').text
        if a.attrib['format'] == "html":
            #print("html answer format")
            at = fixHtmlText(at)
        sc = ET.SubElement(ci, 'simpleChoice', {'identifier': ('alt_' + str(answerindex))})
        sc.text = at
    # add responsetemplate line
    if singleChoice:
        rp = ET.SubElement(tvmc, 'responseProcessing', {'templateLocation': "/templates/RPTEMPLATE_GF.xml"})
    else:
        rp = ET.SubElement(tvmc, 'responseProcessing', {'templateLocation': "/templates/RPTEMPLATE_SCORE.xml"})
    cat = moodlemc.get('qcategory') + '/'
    filename = outputfolder + '/questions/' + cat + qid + '.xml'
    writequestionfile(tvmc, filename)


"""
    produce a Short Answer Fill-In-Blank question numerical/float or shortanswer/string (dpends on qtype)
    todo: check basetype en cardinality multiple answers
    todo: check fraction values in Moodle - what to do in TV?
    todo: handle feedback text - now feedback is skipped
"""
def produceFIBQuestion(moodleShort, qtype, outputfolder):
    ET.register_namespace('', "http://www.imsglobal.org/xsd/imsqti_v2p1")  # no ns0 namespaces here
    fib = ET.fromstring(str(
        '<assessmentItem adaptive="false" timeDependent="false" toolName="Moodle_jand" toolVersion="1.2.3" xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1"></assessmentItem>'))
    # get (random) question number for id
    qid = moodleShort.get('convertix')
    fib.set('identifier', qid)
    title = moodleShort.find('name/text').text
    fib.set('title', title)
    m_qtext = moodleShort.find('questiontext/text').text  # the modified moodle qtext
    ## possible answers (values in correctresponse QTI)
    responseDeclaration = ET.SubElement(fib, 'responseDeclaration',
                                        {'identifier': 'RESPONSE', 'cardinality': 'single', 'baseType': 'string'})
    if qtype == 'numerical':
        responseDeclaration.set('baseType', 'float')

    rd = ET.SubElement(responseDeclaration, 'correctResponse')
    answerPresent = False
    for a in moodleShort.findall('answer'):
        if a.attrib['fraction'] != "100":
            print("NOTE: NON-100 FRACTION VALUE IN " + qid, file=sys.stderr)  ## can TVO handle fractions?? skip it
        else:
            at = a.find('text').text
            # print ('==== ' + at)
            value = ET.SubElement(rd, 'value')
            value.text = at
            answerPresent = True
    if not answerPresent:
        ET.SubElement(rd, 'value').text = "no answer present"

    od = ET.SubElement(fib, 'outcomeDeclaration',
                       {'identifier': "SCORE", 'cardinality': "single", 'baseType': "float", 'normalMinimum': "0",
                        'normalMaximum': "1"})
    ib = ET.SubElement(fib, 'itemBody')
    div1 = ET.SubElement(ib, 'div', {'id': "textBlockId_8765", 'class': "textblock tvblock tvcss_1"})
    ### trick: multiple html tags in comment
    qtext = ET.Comment('-->\n' + m_qtext + '\n<!--')
    div1.append(qtext)
    ed = ET.SubElement(ib, 'extendedTextInteraction', {'responseIdentifier': "RESPONSE"})
    # essay/open question in TVO is just a long TextInteraction?
    if qtype == 'essay':
        ed.set('expectedLength', "6000")
    rp = ET.SubElement(fib, 'responseProcessing', {'templateLocation': "/templates/RPTEMPLATE_GF.xml"})
    cat = moodleShort.get('qcategory') + '/'
    filename = outputfolder + '/questions/' + cat + qid + '.xml'
    writequestionfile(fib, filename)


def writequestionfile(assessmenttree, filename):
    #filename = outputfolder + '/questions/' + qid + '.xml'
    # change 1st line
    f = open(filename, "w")
    f.write('<?xml version="1.0" encoding="utf-8" standalone="yes"?>')
    #ET.dump(questiontree)
    f.write(ET.tostring(assessmenttree, encoding='utf-8', method='xml').decode('utf-8'))
    print(f"Wrote {filename}")


def fixHtmlText(text, convertix=10, prefix='noprefix'):
    text = urllib.parse.unquote(text)
    # text = html.unescape(qt.text)
    # it seems some files have syn-ack-6.png?time=1591350616553" attribute added. Remove it
    text = re.sub('(@@PLUGINFILE@@/[^?]+)\?[^"]+"', '\\1"', text)
    text = re.sub('@@PLUGINFILE@@', "mediafiles", text)
    # lxml html cleaner to fix nested p tags
    page = fromstring(text)
    lxml.html.clean.clean(page)
    text = tostring(page).decode('utf-8')
    ## replace complete img tag with role and size attributes
    text = re.sub('(img src="mediafiles[^"]*")[^>]*>', '\\1 alt="' + prefix + str(convertix) + '" />', text)
    ## some img tags are not closed correctly replace xxx> with xxx/>
    text = re.sub('(<img [^>]*[^/])>', '\\1  />', text)
    text = re.sub('<br>', '<br/>', text)  ## close break tags
    text = re.sub(' dir="ltr"', '', text)  ## dir="ltr" unknown
    text = re.sub('&nbsp;', '', text)  ## nonbreakable space
    text = re.sub('lang="..-.."', '', text)  ## span lang="EN-GB"
    text = re.sub('(span )style="font-size:[^"]*"', '\\1', text)  # span style="font-size: 0.9375rem; illegal
    return text


def createtemplatefiles(outputfolder):
    path = outputfolder + "/templates"
    if not os.path.exists(path): os.makedirs(path)
    shutil.copy2("RPTEMPLATE_GF.xml", outputfolder + "/templates/RPTEMPLATE_GF.xml")
    shutil.copy2("RPTEMPLATE_GF.xml", outputfolder + "/templates/RPTEMPLATE_SCORE.xml")

"""
return the current category name as path and create subfolders
"""
def parseCategory(q, outputfolder):
    ct = q.find("category/text")
    curcategory = ct.text  # like $course$/top/Default for isomecoursename/subcategory #1/subcat/subsubcat name
    curcategory = re.sub('^.course.', 'course', curcategory)
    curcategory = curcategory.strip()
    curcategory = re.sub('  *\/', '/', curcategory)  ## no spaces at end of folder name
    curcategory = re.sub('\/\/', '/', curcategory)  ## no // in path name, single slash
    xx = outputfolder + '/questions/' + curcategory
    print(f"Category path: {xx}")
    try:
        if not os.path.exists(xx):
            os.makedirs(xx)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    return curcategory


def dumpmediafiles(moodlefilename, outputfolder):
    print(f"Exporting media files from {moodlefilename} to folder {outputfolder}")
    path = outputfolder + "/mediafiles"
    if not os.path.exists(path): os.makedirs(path)
    tree = ET.parse(moodlefilename)
    root = tree.getroot()
    i = 1
    for f in root.findall("question/questiontext/file"):
        print("---", i)
        name = f.attrib['name']
        print(f"Reading file {name}")
        fileName = outputfolder + '/mediafiles/' + name
        try:
            image = base64.decodebytes(bytes(f.text, 'utf-8'))
            image_result = open(fileName, 'wb')  # create a writable image and write the decoding result
            image_result.write(image)
        except Exception:                     #binascii.Error
            print(f"cannot decode base64 data for file {fileName}")
        i = i + 1


def convertmoodle(inputfile, outputfolder):
    # produceManifest()
    dumpmediafiles(inputfile, outputfolder)
    createtemplatefiles(outputfolder)
    readMoodle(inputfile, outputfolder)

def main(argv):
    print("Moodle xml questionbank to TextVision converter")
    print("default inputfilename: moodleq.xml")
    print("default outputfolder:  ExportQTI")
    inputfile = 'moodleq.xml'
    outputfolder = 'ExportQTI'
    try:
        opts, args = getopt.getopt(argv, "dfhi:o:", ["ifile=", "ofolder=", "dumpfiles"])
    except getopt.GetoptError:
        print(f'{sys.argv[0]} -i <moodle_xml_filename> -o <outputfoldername>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print(f'Usage: python {sys.argv[0]} -i <moodle_xml_filename> -o <outputfoldername>')
            sys.exit()
        elif opt in ("-i", "--ifile"):
            inputfile = arg
        elif opt in ("-o", "--ofolder"):
            outputfolder = arg
        elif opt in ("-df", "--dumpfiles"):
            dumpmediafiles(inputfile,outputfolder)
            return
    print(f'Input file is "{inputfile}"')
    print(f'Output FOLDER is "{outputfolder}"')
    convertmoodle(inputfile, outputfolder)

if __name__ == "__main__":
    main(sys.argv[1:])
