/* SPDX-License-Identifier: MIT. Smart Install Maker public API/RAM controls. */
#include <xxfclib/formats/smart_install_maker/xx_smart_install_maker.h>
#include <xxfclib/io/xx_io.h>
#include <xxfclib/memory/xx_memory.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks,closed;
#define REQUIRE(x) do{++checks;if(!(x)){fprintf(stderr,"check %u failed line %u: %s\n",checks,__LINE__,#x);goto done;}}while(0)
static ssize_t short_read(xx_io_device *d,void *p,size_t n){return xx_io_read((xx_io_device *)d->priv,p,n>7?7:n);}
static int proxy_seek(xx_io_device *d,int64_t off,int origin){return xx_io_seek64((xx_io_device *)d->priv,off,origin);}
static int64_t proxy_tell(xx_io_device *d){return xx_io_tell((xx_io_device *)d->priv);}
static int64_t proxy_size(xx_io_device *d){return xx_io_size((xx_io_device *)d->priv);}
static int proxy_close(xx_io_device *d){(void)d;++closed;return 0;}
static bool stop_decode(const xx_pd_struct *p,void *user){unsigned *called=(unsigned *)user;int i;for(i=0;i<XX_PD_LEVELS;++i)if(p->records[i].is_busy&&p->records[i].current){++*called;return true;}return false;}
int main(int argc,char **argv){
 xx_io_device *source=NULL,proxy={0};xx_smart_install_maker *archive=NULL;Abstractformat *format=NULL;xx_archive_record_state *state=NULL;xx_io_memory_only_scope scope={0};xx_var limit;xx_pd_struct pd=xx_pd_init();bool scoped=false;unsigned members=0,cancelled=0;int result=1;int64_t base=0;bool expected=true;
 xx_var_init(&limit);REQUIRE(argc>=3);if(argc>3)expected=atoi(argv[3])!=0;if(argc>5)base=strtoll(argv[5],NULL,10);
 REQUIRE((source=xx_io_file_open(argv[1],"rb"))!=NULL);proxy.read=short_read;proxy.seek64=proxy_seek;proxy.tell=proxy_tell;proxy.size=proxy_size;proxy.close=proxy_close;proxy.priv=source;
 REQUIRE(xx_io_seek64(source,11,SEEK_SET)==0);REQUIRE(xx_io_memory_only_begin(&scope,0));scoped=true;REQUIRE((archive=xx_smart_install_maker_create(&proxy,base))!=NULL);format=&archive->format;
 {bool candidate=xx_smart_install_maker_has_candidate_device(&proxy,base);REQUIRE(xx_io_tell(source)==11);if(expected)REQUIRE(candidate);
  REQUIRE(!xx_smart_install_maker_has_candidate_device(&proxy,-1));REQUIRE(xx_io_tell(source)==11);
  REQUIRE(!xx_smart_install_maker_has_candidate_device(&proxy,xx_io_size(source)+1));REQUIRE(xx_io_tell(source)==11);}
 if(argc>4){xx_var_set_u64(&limit,strtoull(argv[4],NULL,10));REQUIRE(xx_format_set_extra_parameter(format,XX_META_ID_OPT_MEMORY_LIMIT,&limit));}
 {bool valid=xx_format_handle_base_info(format,&pd);REQUIRE(xx_io_tell(source)==11);REQUIRE(valid==expected);if(!expected){result=0;goto completed;}}
 REQUIRE((state=xx_format_create_archive_records_reading(format,NULL,&pd))!=NULL);REQUIRE(xx_io_tell(source)==11);
 while(state->has_record){const xx_archive_record *r=xx_format_get_current_archive_record(format,state);REQUIRE(r&&xx_archive_record_get_original_name(r));
  xx_var_set_u64(&limit,1);REQUIRE(xx_format_set_extra_parameter(format,XX_META_ID_OPT_MEMORY_LIMIT,&limit));REQUIRE(!xx_format_unpack_current_archive_record(format,state,&pd));REQUIRE(xx_io_tell(source)==11);REQUIRE(xx_format_remove_extra_parameter(format,XX_META_ID_OPT_MEMORY_LIMIT));
  if(xx_archive_record_get_meta_u64(r,XX_META_ID_UNCOMPRESSED_SIZE,0)>1){REQUIRE(xx_format_set_extra_parameter(format,XX_META_ID_OPT_MAX_MEMBER_SIZE,&limit));REQUIRE(!xx_format_unpack_current_archive_record(format,state,&pd));REQUIRE(xx_format_remove_extra_parameter(format,XX_META_ID_OPT_MAX_MEMBER_SIZE));}
  REQUIRE(xx_format_unpack_current_archive_record(format,state,&pd));REQUIRE(xx_io_tell(source)==11);++members;if(!xx_format_archive_record_move_to_next(format,state,&pd))break;}
 REQUIRE(members==state->total_records);xx_format_free_archive_records_reading(format,state);state=NULL;
 {xx_pd_struct stopped=xx_pd_init();xx_pd_stop(&stopped);REQUIRE(!format->check_is_valid(format,&stopped));REQUIRE(xx_io_tell(source)==11);}
 {xx_pd_struct input_pd=xx_pd_init();unsigned stopped_input=0;xx_pd_observer prior=xx_pd_set_observer(&input_pd,stop_decode,&stopped_input);REQUIRE(!format->check_is_valid(format,&input_pd));REQUIRE(stopped_input>0&&xx_pd_is_stopped(&input_pd));xx_pd_set_observer(prior.progress,prior.callback,prior.user_data);REQUIRE(xx_io_tell(source)==11);}
 REQUIRE((state=xx_format_create_archive_records_reading(format,NULL,&pd))!=NULL);
 {xx_pd_observer prior=xx_pd_set_observer(&pd,stop_decode,&cancelled);REQUIRE(!xx_format_unpack_current_archive_record(format,state,&pd));REQUIRE(cancelled>0&&xx_pd_is_stopped(&pd));xx_pd_set_observer(prior.progress,prior.callback,prior.user_data);}
 REQUIRE(xx_io_tell(source)==11);xx_format_free_archive_records_reading(format,state);state=NULL;pd=xx_pd_init();
completed:
 REQUIRE(xx_io_memory_only_used()==0);REQUIRE(xx_io_memory_only_end(&scope));scoped=false;
 if(expected&&argv[2][0]){xx_list_s options;xx_meta path;size_t n=strlen(argv[2]);char *borrowed=(char *)xx_mem_alloc(n?n:1);REQUIRE(borrowed!=NULL);if(n)memcpy(borrowed,argv[2],n);REQUIRE(xx_list_init(&options,sizeof(xx_meta),xx_meta_free_elem));xx_meta_init(&path,XX_META_ID_OPT_UNPACK_PATH);xx_var_set_str_view(&path.var,borrowed,n);REQUIRE(xx_list_append(&options,&path));state=xx_format_create_archive_records_reading(format,&options,&pd);xx_list_cleanup(&options);xx_mem_free(borrowed);REQUIRE(state!=NULL);
  while(state->has_record){REQUIRE(xx_format_unpack_current_archive_record(format,state,&pd));REQUIRE(xx_io_tell(source)==11);if(!xx_format_archive_record_move_to_next(format,state,&pd))break;}}
 REQUIRE(!closed);printf("{\"checks\":%u,\"members\":%u,\"memory_only\":true,\"cursor_restored\":true,\"short_reads\":true}\n",checks,members);result=0;
done:if(state)xx_format_free_archive_records_reading(format,state);xx_smart_install_maker_free(archive);xx_var_cleanup(&limit);if(source)xx_io_close(source);if(scoped)(void)xx_io_memory_only_end(&scope);return result;
}
