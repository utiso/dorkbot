FROM ubuntu

RUN mkdir -p /opt/
COPY . /opt/dorkbot
 
RUN apt update && apt install -yqq python python-pip libpq-dev phantomjs git ruby ruby-dev zlib1g-dev curl
RUN cd /opt/dorkbot && python /opt/dorkbot/setup.py install
RUN cd /opt && git clone https://github.com/catatonicprime/arachni
RUN gem install bundler
RUN cd /opt/arachni && bundler install
