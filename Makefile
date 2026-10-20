.PHONY: demo langgraph-demo reverse-demo test clean

demo:
	python3 -m schemashift demo --approve

langgraph-demo:
	python3 -m schemashift.langgraph_app --approve

reverse-demo:
	python3 -m schemashift.langgraph_reverse_app --approve

test:
	python3 -m unittest discover -s tests -v

clean:
	python3 -m schemashift clean
