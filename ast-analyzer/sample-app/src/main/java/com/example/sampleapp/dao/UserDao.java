package com.example.sampleapp.dao;

import com.example.sampleapp.model.User;
import org.apache.ibatis.annotations.Mapper;
import java.util.List;

@Mapper
public interface UserDao {
    User findByUsername(String username);
    User findById(Integer id);
    List<User> findAll();
    int insert(User user);
    int update(User user);
}
